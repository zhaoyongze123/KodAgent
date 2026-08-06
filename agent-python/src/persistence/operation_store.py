"""PostgreSQL repository for Operation and Effect runtime facts.

The repository is intentionally independent from LangGraph checkpoint APIs.
One database transaction owns the version check and the state transition; Redis
is not involved in the source-of-truth path.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from ..domain.effect import (
    EffectRecord,
    EffectStatus,
    EffectTransitionError,
    transition_effect,
)
from ..domain.events import EventEnvelope, RuntimeOutboxRecord
from ..domain.operation import (
    OperationContext,
    OperationStatus,
    OperationTransitionError,
    patch_operation,
    transition_operation,
)


class OperationConcurrencyError(RuntimeError):
    """Raised when a row changed since the caller loaded it."""


def runtime_postgres_dsn() -> str:
    dsn = os.getenv("OA_AGENT_RUNTIME_POSTGRES_URI") or os.getenv("LANGGRAPH_POSTGRES_URI")
    if not dsn:
        raise RuntimeError("未配置 OA_AGENT_RUNTIME_POSTGRES_URI 或 LANGGRAPH_POSTGRES_URI")
    return dsn


class OperationStore:
    """Transactional store for the Python-owned runtime aggregates."""

    def __init__(self, dsn: str | None = None, *, pool: ConnectionPool | None = None) -> None:
        self._owns_pool = pool is None
        self._pool = pool or ConnectionPool(
            conninfo=dsn or runtime_postgres_dsn(),
            kwargs={"row_factory": dict_row, "prepare_threshold": 0},
            min_size=int(os.getenv("OA_AGENT_RUNTIME_POOL_MIN", "1")),
            max_size=int(os.getenv("OA_AGENT_RUNTIME_POOL_MAX", "5")),
            open=False,
        )
        self._pool.open(wait=True)

    def close(self) -> None:
        if self._owns_pool:
            self._pool.close()

    @contextmanager
    def _connection(self) -> Iterator:
        with self._pool.connection() as connection:
            yield connection

    def create_operation(self, operation: OperationContext) -> OperationContext:
        with self._connection() as connection, connection.transaction():
            row = connection.execute(
                """
                INSERT INTO agent_runtime.operation (
                    operation_id, action_id, capability_id, tenant_id, user_id,
                    thread_id, origin_run_id, current_run_id, message_id,
                    status, version, payload_schema_version, payload, result,
                    plan_id, plan_revision, approval_id, expires_at,
                    created_at, updated_at
                ) VALUES (
                    %(operation_id)s, %(action_id)s, %(capability_id)s,
                    %(tenant_id)s, %(user_id)s, %(thread_id)s,
                    %(origin_run_id)s, %(current_run_id)s, %(message_id)s,
                    %(status)s, %(version)s, %(payload_schema_version)s,
                    %(payload)s, %(result)s, %(plan_id)s, %(plan_revision)s,
                    %(approval_id)s, %(expires_at)s, %(created_at)s,
                    %(updated_at)s
                )
                ON CONFLICT (operation_id) DO NOTHING
                RETURNING *
                """,
                self._operation_params(operation),
            ).fetchone()
            if not row:
                row = connection.execute(
                    "SELECT * FROM agent_runtime.operation WHERE operation_id = %s",
                    (operation.operation_id,),
                ).fetchone()
                if not row:
                    raise OperationConcurrencyError("Operation 幂等插入失败且无法读取已存在记录")
                existing = self._operation(row)
                identity_fields = (
                    "action_id", "capability_id", "tenant_id", "user_id",
                    "thread_id", "message_id",
                )
                if any(getattr(existing, field) != getattr(operation, field) for field in identity_fields):
                    raise ValueError(f"Operation ID 已绑定到不同的业务上下文: {operation.operation_id}")
        return self._operation(row)

    def get_operation(self, operation_id: str, *, for_update: bool = False) -> OperationContext | None:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection() as connection:
            row = connection.execute(
                f"SELECT * FROM agent_runtime.operation WHERE operation_id = %s{suffix}",
                (operation_id,),
            ).fetchone()
        return self._operation(row) if row else None

    def find_operations(
        self,
        *,
        action_id: str,
        statuses: set[str] | frozenset[str],
        tenant_id: str,
        user_id: str,
        thread_id: str,
        message_id: str,
        origin_run_id: str,
    ) -> list[OperationContext]:
        """Find durable Operations by their trusted request envelope.

        This is a recovery lookup, not a replacement for ``operation_id``.
        Callers must reject an ambiguous result instead of selecting the most
        recent row, because one Thread may legitimately contain concurrent
        Operations.
        """
        normalized_statuses = [str(value).strip() for value in statuses if str(value).strip()]
        if not normalized_statuses:
            return []
        placeholders = ", ".join(["%s"] * len(normalized_statuses))
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM agent_runtime.operation
                WHERE action_id = %s
                  AND status IN ({placeholders})
                  AND tenant_id = %s
                  AND user_id = %s
                  AND thread_id = %s
                  AND message_id = %s
                  AND origin_run_id = %s
                ORDER BY updated_at DESC, operation_id
                """,
                (
                    action_id,
                    *normalized_statuses,
                    tenant_id,
                    user_id,
                    thread_id,
                    message_id,
                    origin_run_id,
                ),
            ).fetchall()
        return [self._operation(row) for row in rows]

    def transition_operation(
        self,
        operation_id: str,
        target: OperationStatus,
        *,
        expected_version: int | None,
        run_id: str | None = None,
        causation_id: str | None = None,
        now: datetime | None = None,
        event: EventEnvelope | None = None,
    ) -> OperationContext:
        with self._connection() as connection, connection.transaction():
            row = connection.execute(
                "SELECT * FROM agent_runtime.operation WHERE operation_id = %s FOR UPDATE",
                (operation_id,),
            ).fetchone()
            if not row:
                raise KeyError(f"Operation 不存在: {operation_id}")
            current = self._operation(row)
            try:
                updated = transition_operation(
                    current, target, expected_version=expected_version, now=now,
                )
            except OperationTransitionError:
                raise
            updated_row = connection.execute(
                """
                UPDATE agent_runtime.operation
                SET status = %s, version = %s, updated_at = %s
                WHERE operation_id = %s AND version = %s
                RETURNING *
                """,
                (updated.status, updated.version, updated.updated_at,
                 operation_id, current.version),
            ).fetchone()
            if not updated_row:
                raise OperationConcurrencyError(f"Operation 版本竞争: {operation_id}")
            connection.execute(
                """
                INSERT INTO agent_runtime.operation_transition (
                    operation_id, from_status, to_status, from_version,
                    to_version, run_id, causation_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (operation_id, current.status, updated.status, current.version,
                 updated.version, run_id, causation_id),
            )
            if event is not None:
                self._insert_event(connection, event)
        return self._operation(updated_row)

    def patch_operation(
        self,
        operation_id: str,
        *,
        expected_version: int | None,
        current_run_id: str | None = None,
        payload: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        approval_id: str | None = None,
        now: datetime | None = None,
        event: EventEnvelope | None = None,
    ) -> OperationContext:
        """Persist non-state fields with the same optimistic-lock boundary."""

        with self._connection() as connection, connection.transaction():
            row = connection.execute(
                "SELECT * FROM agent_runtime.operation WHERE operation_id = %s FOR UPDATE",
                (operation_id,),
            ).fetchone()
            if not row:
                raise KeyError(f"Operation 不存在: {operation_id}")
            current = self._operation(row)
            updated = patch_operation(
                current,
                expected_version=expected_version,
                current_run_id=current_run_id,
                payload=payload,
                result=result,
                approval_id=approval_id,
                now=now,
            )
            updated_row = connection.execute(
                """
                UPDATE agent_runtime.operation
                SET current_run_id = %s, payload = %s, result = %s,
                    approval_id = %s, version = %s, updated_at = %s
                WHERE operation_id = %s AND version = %s
                RETURNING *
                """,
                (
                    updated.current_run_id,
                    Jsonb(updated.payload),
                    Jsonb(updated.result),
                    updated.approval_id,
                    updated.version,
                    updated.updated_at,
                    operation_id,
                    current.version,
                ),
            ).fetchone()
            if not updated_row:
                raise OperationConcurrencyError(f"Operation 版本竞争: {operation_id}")
            if event is not None:
                self._insert_event(connection, event)
        return self._operation(updated_row)

    def bind_approval(
        self,
        operation_id: str,
        approval_id: str,
        *,
        expected_version: int | None,
        now: datetime | None = None,
        event: EventEnvelope | None = None,
    ) -> OperationContext:
        """Bind a Java-owned Approval without changing Operation status."""

        return self.patch_operation(
            operation_id,
            expected_version=expected_version,
            approval_id=approval_id,
            now=now,
            event=event,
        )

    def create_effect(self, effect: EffectRecord, *, event: EventEnvelope | None = None) -> EffectRecord:
        with self._connection() as connection, connection.transaction():
            row = connection.execute(
                """
                INSERT INTO agent_runtime.effect (
                    effect_id, operation_id, action_id, idempotency_key,
                    request_hash, status, attempt, lease_owner, lease_until,
                    reconcile_strategy, request_data, response_data,
                    error_data, version, created_at, updated_at
                ) VALUES (
                    %(effect_id)s, %(operation_id)s, %(action_id)s,
                    %(idempotency_key)s, %(request_hash)s, %(status)s,
                    %(attempt)s, %(lease_owner)s, %(lease_until)s,
                    %(reconcile_strategy)s, %(request_data)s,
                    %(response_data)s, %(error_data)s, %(version)s,
                    %(created_at)s, %(updated_at)s
                )
                ON CONFLICT (operation_id, idempotency_key) DO NOTHING
                RETURNING *
                """,
                self._effect_params(effect),
            ).fetchone()
            if not row:
                row = connection.execute(
                    """
                    SELECT * FROM agent_runtime.effect
                    WHERE operation_id = %s AND idempotency_key = %s
                    """,
                    (effect.operation_id, effect.idempotency_key),
                ).fetchone()
                if not row:
                    raise OperationConcurrencyError("Effect 幂等插入失败且无法读取已存在记录")
                existing = self._effect(row)
                if existing.request_hash != effect.request_hash:
                    raise ValueError(
                        f"Effect 幂等键复用但请求摘要不同: {effect.idempotency_key}"
                    )
                return existing
            if event is not None:
                self._insert_event(connection, event)
        return self._effect(row)

    def get_effect(self, effect_id: str, *, for_update: bool = False) -> EffectRecord | None:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection() as connection:
            row = connection.execute(
                f"SELECT * FROM agent_runtime.effect WHERE effect_id = %s{suffix}",
                (effect_id,),
            ).fetchone()
        return self._effect(row) if row else None

    def get_effect_by_idempotency_key(
        self,
        operation_id: str,
        idempotency_key: str,
        *,
        for_update: bool = False,
    ) -> EffectRecord | None:
        """Load the one effect for an operation without scanning its history."""

        suffix = " FOR UPDATE" if for_update else ""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM agent_runtime.effect "
                f"WHERE operation_id = %s AND idempotency_key = %s{suffix}",
                (operation_id, idempotency_key),
            ).fetchone()
        return self._effect(row) if row else None

    def transition_effect(
        self,
        effect_id: str,
        target: EffectStatus,
        *,
        expected_version: int | None,
        response_data: dict | None = None,
        error_data: dict | None = None,
        now: datetime | None = None,
        event: EventEnvelope | None = None,
    ) -> EffectRecord:
        with self._connection() as connection, connection.transaction():
            row = connection.execute(
                "SELECT * FROM agent_runtime.effect WHERE effect_id = %s FOR UPDATE",
                (effect_id,),
            ).fetchone()
            if not row:
                raise KeyError(f"Effect 不存在: {effect_id}")
            current = self._effect(row)
            updated = transition_effect(
                current, target, expected_version=expected_version, now=now,
            )
            if response_data is not None:
                updated = updated.model_copy(update={"response_data": response_data})
            if error_data is not None:
                updated = updated.model_copy(update={"error_data": error_data})
            updated_row = connection.execute(
                """
                UPDATE agent_runtime.effect
                SET status = %s, version = %s, response_data = %s,
                    error_data = %s, lease_owner = %s, lease_until = %s,
                    updated_at = %s
                WHERE effect_id = %s AND version = %s
                RETURNING *
                """,
                (updated.status, updated.version, Jsonb(updated.response_data),
                 Jsonb(updated.error_data), updated.lease_owner,
                 updated.lease_until, updated.updated_at, effect_id,
                 current.version),
            ).fetchone()
            if not updated_row:
                raise OperationConcurrencyError(f"Effect 版本竞争: {effect_id}")
            if event is not None:
                self._insert_event(connection, event)
        return self._effect(updated_row)

    def claim_effect(
        self,
        effect_id: str,
        *,
        lease_owner: str,
        lease_until: datetime,
        expected_version: int | None,
        now: datetime | None = None,
        event: EventEnvelope | None = None,
    ) -> EffectRecord:
        """Claim only planned/retryable work; never steal unknown side effects."""

        with self._connection() as connection, connection.transaction():
            row = connection.execute(
                "SELECT * FROM agent_runtime.effect WHERE effect_id = %s FOR UPDATE",
                (effect_id,),
            ).fetchone()
            if not row:
                raise KeyError(f"Effect 不存在: {effect_id}")
            current = self._effect(row)
            if current.status not in {"PLANNED", "FAILED_RETRYABLE"}:
                raise EffectTransitionError(
                    f"Effect {effect_id} 不能 Claim: {current.status}"
                )
            claimed = transition_effect(
                current, "CLAIMED", expected_version=expected_version, now=now,
            ).model_copy(update={
                "attempt": current.attempt + 1,
                "lease_owner": lease_owner,
                "lease_until": lease_until,
            })
            updated_row = connection.execute(
                """
                UPDATE agent_runtime.effect
                SET status = %s, attempt = %s, lease_owner = %s,
                    lease_until = %s, version = %s, updated_at = %s
                WHERE effect_id = %s AND version = %s
                RETURNING *
                """,
                (claimed.status, claimed.attempt, claimed.lease_owner,
                 claimed.lease_until, claimed.version, claimed.updated_at,
                 effect_id, current.version),
            ).fetchone()
            if not updated_row:
                raise OperationConcurrencyError(f"Effect Claim 版本竞争: {effect_id}")
            if event is not None:
                self._insert_event(connection, event)
        return self._effect(updated_row)

    def append_event(self, event: EventEnvelope) -> EventEnvelope:
        """Append a runtime fact to the durable outbox idempotently.

        The outbox payload contains the complete versioned envelope. A future
        publisher may project it to Java/SSE without reconstructing facts from
        narration text or LangGraph checkpoints.
        """

        with self._connection() as connection, connection.transaction():
            self._insert_event(connection, event)
        return event

    def claim_outbox(
        self,
        *,
        lease_owner: str,
        lease_until: datetime,
        limit: int = 50,
        max_attempts: int = 10,
        now: datetime | None = None,
        aggregate_id: str | None = None,
    ) -> list[RuntimeOutboxRecord]:
        """Claim pending runtime facts safely across multiple workers.

        Claiming increments ``attempts`` in the same transaction as the row
        lock.  An expired lease is reclaimable, but a published or dead-letter
        row is never handed to another worker.
        """

        if not lease_owner.strip():
            raise ValueError("lease_owner cannot be blank")
        if limit < 1:
            return []
        attempts_limit = max(1, int(max_attempts))
        timestamp = now or datetime.now(timezone.utc)
        with self._connection() as connection, connection.transaction():
            connection.execute(
                """
                UPDATE agent_runtime.outbox
                SET dead_lettered_at = COALESCE(dead_lettered_at, %s),
                    lease_owner = NULL, lease_until = NULL,
                    last_error = COALESCE(last_error, 'outbox max attempts exhausted')
                WHERE published_at IS NULL AND dead_lettered_at IS NULL
                  AND attempts >= %s
                  AND (lease_until IS NULL OR lease_until <= %s)
                """,
                (timestamp, attempts_limit, timestamp),
            )
            rows = connection.execute(
                """
                WITH candidates AS (
                    SELECT event_id
                    FROM agent_runtime.outbox
                    WHERE published_at IS NULL
                      AND dead_lettered_at IS NULL
                      AND next_attempt_at <= %s
                      AND (lease_until IS NULL OR lease_until <= %s)
                      AND attempts < %s
                      AND (%s::varchar IS NULL OR aggregate_id = %s)
                    ORDER BY created_at, event_id
                    FOR UPDATE SKIP LOCKED
                    LIMIT %s
                )
                UPDATE agent_runtime.outbox AS outbox
                SET attempts = outbox.attempts + 1,
                    lease_owner = %s,
                    lease_until = %s
                FROM candidates
                WHERE outbox.event_id = candidates.event_id
                RETURNING outbox.*
                """,
                (
                    timestamp,
                    timestamp,
                    attempts_limit,
                    aggregate_id,
                    aggregate_id,
                    limit,
                    lease_owner,
                    lease_until,
                ),
            ).fetchall()
        return [self._outbox(row) for row in rows]

    def renew_outbox_lease(
        self,
        event_id: str,
        *,
        lease_owner: str,
        lease_until: datetime,
    ) -> bool:
        """Extend a live claim without changing the delivery attempt."""

        with self._connection() as connection, connection.transaction():
            updated = connection.execute(
                """
                UPDATE agent_runtime.outbox
                SET lease_until = %s
                WHERE event_id = %s AND lease_owner = %s
                  AND published_at IS NULL AND dead_lettered_at IS NULL
                """,
                (lease_until, event_id, lease_owner),
            ).rowcount
        return updated == 1

    def mark_outbox_published(self, event_id: str, *, lease_owner: str, now: datetime | None = None) -> bool:
        """Acknowledge a claimed delivery; stale workers cannot acknowledge it."""

        timestamp = now or datetime.now(timezone.utc)
        with self._connection() as connection, connection.transaction():
            updated = connection.execute(
                """
                UPDATE agent_runtime.outbox
                SET published_at = %s, lease_owner = NULL, lease_until = NULL
                WHERE event_id = %s AND lease_owner = %s
                  AND published_at IS NULL AND dead_lettered_at IS NULL
                """,
                (timestamp, event_id, lease_owner),
            ).rowcount
        return updated == 1

    def mark_outbox_failed(
        self,
        event_id: str,
        *,
        lease_owner: str,
        error: str,
        next_attempt_at: datetime,
        max_attempts: int = 10,
        now: datetime | None = None,
    ) -> bool:
        """Release a claim and schedule retry, or move it to dead letter."""

        timestamp = now or datetime.now(timezone.utc)
        attempts_limit = max(1, int(max_attempts))
        with self._connection() as connection, connection.transaction():
            updated = connection.execute(
                """
                UPDATE agent_runtime.outbox
                SET lease_owner = NULL,
                    lease_until = NULL,
                    next_attempt_at = %s,
                    last_error = %s,
                    dead_lettered_at = CASE
                        WHEN attempts >= %s THEN COALESCE(dead_lettered_at, %s)
                        ELSE NULL
                    END
                WHERE event_id = %s AND lease_owner = %s
                  AND published_at IS NULL AND dead_lettered_at IS NULL
                """,
                (
                    next_attempt_at,
                    str(error)[:1000],
                    attempts_limit,
                    timestamp,
                    event_id,
                    lease_owner,
                ),
            ).rowcount
        return updated == 1

    @staticmethod
    def _insert_event(connection, event: EventEnvelope) -> None:
        connection.execute(
            """
            INSERT INTO agent_runtime.outbox (
                event_id, source, aggregate_type, aggregate_id,
                aggregate_version, payload
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                event.event_id,
                event.source,
                event.aggregate_type,
                event.aggregate_id,
                event.aggregate_version,
                Jsonb(event.model_dump(mode="json")),
            ),
        )

    @staticmethod
    def _outbox(row: dict) -> RuntimeOutboxRecord:
        return RuntimeOutboxRecord.model_validate(dict(row))

    @staticmethod
    def _operation_params(operation: OperationContext) -> dict:
        return {
            **operation.model_dump(),
            "payload": Jsonb(operation.payload),
            "result": Jsonb(operation.result),
        }

    @staticmethod
    def _effect_params(effect: EffectRecord) -> dict:
        return {
            **effect.model_dump(),
            "request_data": Jsonb(effect.request_data),
            "response_data": Jsonb(effect.response_data),
            "error_data": Jsonb(effect.error_data),
        }

    @staticmethod
    def _operation(row: dict) -> OperationContext:
        return OperationContext.model_validate(dict(row))

    @staticmethod
    def _effect(row: dict) -> EffectRecord:
        return EffectRecord.model_validate(dict(row))


__all__ = ["OperationConcurrencyError", "OperationStore", "runtime_postgres_dsn"]
