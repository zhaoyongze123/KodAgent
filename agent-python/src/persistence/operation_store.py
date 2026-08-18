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
from ..domain.coordination import (
    CoordinationBatch,
    CoordinationBatchStatus,
    CoordinationStep,
    CoordinationStepStatus,
    CoordinationTransitionError,
    transition_batch,
    transition_step,
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

    # ------------------------------------------------------------------
    # 跨领域协作批次
    # ------------------------------------------------------------------
    # 这组方法与 Operation 存储在同一个事务库中，但刻意不复用 Operation 表：
    # 一个 Batch 可以有多项独立业务操作，而每一项仍需保留自己的幂等和 HITL
    # 生命周期。Batch 只记录 DAG 调度及跨 Agent 汇总事实。

    def create_coordination_batch(
        self,
        batch: CoordinationBatch,
        *,
        event: EventEnvelope | None = None,
    ) -> CoordinationBatch:
        """创建协作批次及其不可变步骤图；同一 batch ID 可幂等重试。"""

        with self._connection() as connection, connection.transaction():
            row = connection.execute(
                """
                INSERT INTO agent_runtime.coordination_batch (
                    batch_id, tenant_id, user_id, thread_id, origin_run_id,
                    current_run_id, message_id, request_summary, status,
                    version, created_at, updated_at
                ) VALUES (
                    %(batch_id)s, %(tenant_id)s, %(user_id)s, %(thread_id)s,
                    %(origin_run_id)s, %(current_run_id)s, %(message_id)s,
                    %(request_summary)s, %(status)s, %(version)s,
                    %(created_at)s, %(updated_at)s
                )
                ON CONFLICT (batch_id) DO NOTHING
                RETURNING *
                """,
                self._coordination_batch_params(batch),
            ).fetchone()
            if row is None:
                existing = self._get_coordination_batch(connection, batch.batch_id, for_update=True)
                if existing is None:
                    raise OperationConcurrencyError("协作批次幂等插入失败且无法读取已存在记录")
                identity_fields = ("tenant_id", "user_id", "thread_id", "message_id", "origin_run_id")
                if any(getattr(existing, name) != getattr(batch, name) for name in identity_fields):
                    raise ValueError(f"协作批次 ID 已绑定到不同请求上下文: {batch.batch_id}")
                if tuple(step.step_id for step in existing.steps) != tuple(step.step_id for step in batch.steps):
                    raise ValueError(f"协作批次 ID 已绑定到不同步骤图: {batch.batch_id}")
                return existing
            for step in batch.steps:
                connection.execute(
                    """
                    INSERT INTO agent_runtime.coordination_step (
                        batch_id, step_id, domain, action_id, executor_tool,
                        work_order, depends_on, failure_policy, status,
                        version, operation_id, receipt, error_code, error_message,
                        started_at, completed_at
                    ) VALUES (
                        %(batch_id)s, %(step_id)s, %(domain)s, %(action_id)s,
                        %(executor_tool)s, %(work_order)s, %(depends_on)s,
                        %(failure_policy)s, %(status)s, %(version)s, %(operation_id)s,
                        %(receipt)s, %(error_code)s, %(error_message)s,
                        %(started_at)s, %(completed_at)s
                    )
                    """,
                    self._coordination_step_params(batch.batch_id, step),
                )
            if event is not None:
                self._insert_event(connection, event)
        return self.get_coordination_batch(batch.batch_id, required=True)

    def get_coordination_batch(
        self,
        batch_id: str,
        *,
        required: bool = False,
    ) -> CoordinationBatch | None:
        """读取批次及其完整步骤图；不从 checkpoint 或展示消息还原状态。"""

        with self._connection() as connection:
            batch = self._get_coordination_batch(connection, batch_id)
        if batch is None and required:
            raise KeyError(f"协作批次不存在: {batch_id}")
        return batch

    def transition_coordination_batch(
        self,
        batch_id: str,
        target: CoordinationBatchStatus,
        *,
        expected_version: int | None,
        run_id: str | None = None,
        event: EventEnvelope | None = None,
        now: datetime | None = None,
    ) -> CoordinationBatch:
        """推进批次状态；步骤状态必须由 ``transition_coordination_step`` 修改。"""

        with self._connection() as connection, connection.transaction():
            current = self._get_coordination_batch(connection, batch_id, for_update=True)
            if current is None:
                raise KeyError(f"协作批次不存在: {batch_id}")
            updated = transition_batch(current, target, expected_version=expected_version, now=now)
            row = connection.execute(
                """
                UPDATE agent_runtime.coordination_batch
                SET status = %s, version = %s, current_run_id = %s, updated_at = %s
                WHERE batch_id = %s AND version = %s
                RETURNING *
                """,
                (
                    updated.status, updated.version, run_id or updated.current_run_id,
                    updated.updated_at, batch_id, current.version,
                ),
            ).fetchone()
            if row is None:
                raise OperationConcurrencyError(f"协作批次版本竞争: {batch_id}")
            if event is not None:
                self._insert_event(connection, event)
        return self.get_coordination_batch(batch_id, required=True)

    def transition_coordination_step(
        self,
        batch_id: str,
        step_id: str,
        target: CoordinationStepStatus,
        *,
        receipt: dict[str, Any] | None = None,
        operation_id: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        event: EventEnvelope | None = None,
        now: datetime | None = None,
    ) -> CoordinationBatch:
        """原子更新一个步骤；调用方必须先依据依赖图确认该步骤可运行。"""

        with self._connection() as connection, connection.transaction():
            batch = self._get_coordination_batch(connection, batch_id, for_update=True)
            if batch is None:
                raise KeyError(f"协作批次不存在: {batch_id}")
            current_step = next((step for step in batch.steps if step.step_id == step_id), None)
            if current_step is None:
                raise KeyError(f"协作步骤不存在: {batch_id}/{step_id}")
            updated_step = transition_step(
                current_step, target, now=now, receipt=receipt,
                operation_id=operation_id, error_code=error_code,
                error_message=error_message,
            )
            connection.execute(
                """
                UPDATE agent_runtime.coordination_step
                SET status = %s, version = %s, operation_id = %s, receipt = %s,
                    error_code = %s, error_message = %s, started_at = %s,
                    completed_at = %s
                WHERE batch_id = %s AND step_id = %s
                """,
                (
                    updated_step.status, updated_step.version, updated_step.operation_id,
                    Jsonb(updated_step.receipt) if updated_step.receipt is not None else None,
                    updated_step.error_code, updated_step.error_message,
                    updated_step.started_at, updated_step.completed_at,
                    batch_id, step_id,
                ),
            )
            if event is not None:
                self._insert_event(connection, event)
        return self.get_coordination_batch(batch_id, required=True)

    def coordination_batches_for_operation(self, operation_id: str) -> list[CoordinationBatch]:
        """查询引用某个领域 Operation 的协作批次。

        ``CoordinationStep.operation_id`` 仅在子 Agent 成功生成草稿后写入，因此
        此查询用于确认卡完成后的状态回收，不能反向作为“定位业务对象”的来源。
        返回完整批次，让调用方继续使用同一套版本化状态迁移。
        """

        if not str(operation_id or "").strip():
            return []
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT batch_id
                FROM agent_runtime.coordination_step
                WHERE operation_id = %s
                ORDER BY batch_id
                """,
                (operation_id,),
            ).fetchall()
            batches = [
                self._get_coordination_batch(connection, str(row["batch_id"]))
                for row in rows
            ]
        return [batch for batch in batches if batch is not None]

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
    def _coordination_batch_params(batch: CoordinationBatch) -> dict:
        """转换 Pydantic 批次字段为 PostgreSQL 参数，不把 steps 写进父表。"""

        return {
            "batch_id": batch.batch_id,
            "tenant_id": batch.tenant_id,
            "user_id": batch.user_id,
            "thread_id": batch.thread_id,
            "origin_run_id": batch.origin_run_id,
            "current_run_id": batch.current_run_id,
            "message_id": batch.message_id,
            "request_summary": batch.request_summary,
            "status": batch.status,
            "version": batch.version,
            "created_at": batch.created_at,
            "updated_at": batch.updated_at,
        }

    @staticmethod
    def _coordination_step_params(batch_id: str, step: CoordinationStep) -> dict:
        """转换一个步骤；结构化 WorkOrder/依赖/回执均以 JSONB 保存。"""

        return {
            "batch_id": batch_id,
            "step_id": step.step_id,
            "domain": step.domain,
            "action_id": step.action_id,
            "executor_tool": step.executor_tool,
            "work_order": Jsonb(step.work_order),
            "depends_on": Jsonb(list(step.depends_on)),
            "failure_policy": step.failure_policy,
            "status": step.status,
            "version": step.version,
            "operation_id": step.operation_id,
            "receipt": Jsonb(step.receipt) if step.receipt is not None else None,
            "error_code": step.error_code,
            "error_message": step.error_message,
            "started_at": step.started_at,
            "completed_at": step.completed_at,
        }

    @classmethod
    def _get_coordination_batch(cls, connection, batch_id: str, *, for_update: bool = False) -> CoordinationBatch | None:
        suffix = " FOR UPDATE" if for_update else ""
        row = connection.execute(
            f"SELECT * FROM agent_runtime.coordination_batch WHERE batch_id = %s{suffix}",
            (batch_id,),
        ).fetchone()
        if row is None:
            return None
        step_rows = connection.execute(
            """
            SELECT * FROM agent_runtime.coordination_step
            WHERE batch_id = %s ORDER BY step_id
            """,
            (batch_id,),
        ).fetchall()
        data = dict(row)
        data["steps"] = tuple(cls._coordination_step(step_row) for step_row in step_rows)
        return CoordinationBatch.model_validate(data)

    @staticmethod
    def _coordination_step(row: dict) -> CoordinationStep:
        data = dict(row)
        # ``batch_id`` 是关系表的父键，领域 Step 已由其所属 Batch 表达该关系；
        # 不能透传给 extra=forbid 的不可变业务模型。
        data.pop("batch_id", None)
        data["depends_on"] = tuple(data.get("depends_on") or ())
        return CoordinationStep.model_validate(data)

    @staticmethod
    def _operation(row: dict) -> OperationContext:
        return OperationContext.model_validate(dict(row))

    @staticmethod
    def _effect(row: dict) -> EffectRecord:
        return EffectRecord.model_validate(dict(row))


__all__ = ["OperationConcurrencyError", "OperationStore", "runtime_postgres_dsn"]
