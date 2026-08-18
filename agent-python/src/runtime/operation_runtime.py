"""Bridge deterministic workflows to the durable Operation/Effect kernel.

The bridge owns no domain rules. It only translates workflow lifecycle points
into the stable runtime aggregates and binds the resulting operation ID to the
request-scoped Agent context. A missing DSN is tolerated for isolated unit
tests and local legacy paths; production can set
``OA_AGENT_RUNTIME_REQUIRED=true`` to fail closed.
"""

from __future__ import annotations

import hashlib
import json
import os
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..domain.effect import EffectRecord, EffectStatus
from ..domain.events import EventEnvelope
from ..domain.operation import OperationContext, OperationStatus
from ..persistence.operation_store import OperationStore
from ..tools.common.events import current_agent_context, set_operation_context


_ACTIVE_OPERATION: ContextVar["OperationRuntime | None"] = ContextVar(
    "active_operation_runtime", default=None,
)


def action_id_for(capability_id: str, operation: str) -> str:
    """Compile a domain verb into the stable Action ID namespace."""

    capability = str(capability_id or "").strip().lower()
    prefix = {
        "personal_schedule": "schedule",
        "schedule": "schedule",
        "meeting": "meeting",
    }.get(capability, capability)
    if not prefix:
        raise ValueError("capability_id cannot be blank")
    verb = str(operation or "CREATE").strip().upper()
    if verb not in {"CREATE", "UPDATE", "CANCEL", "DELETE"}:
        raise ValueError(f"不支持的 Operation 动词: {operation}")
    return f"{prefix}.{verb.lower()}"


def _required_runtime() -> bool:
    return os.getenv("OA_AGENT_RUNTIME_REQUIRED", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


class AgentContextIncompleteError(RuntimeError):
    """Raised when the request envelope lacks identity fields needed to persist an Operation."""

    error_code = "AGENT_CONTEXT_MISSING"
    user_message = "当前请求缺少必要的对话上下文（用户身份/会话/消息），无法完成写入操作，请重新发起对话。"

    def __init__(self, missing: list[str]) -> None:
        self.missing = list(missing)
        super().__init__("Agent 上下文不完整，缺少字段: " + ", ".join(self.missing))


def _missing_context_fields(context: dict[str, str]) -> list[str]:
    required = ("tenantId", "userId", "threadId", "runId", "messageId")
    return [key for key in required if not str(context.get(key) or "").strip()]


def _deterministic_operation_id(
    context: dict[str, str], action_id: str, operation_key: str | None = None,
) -> str:
    identity = "|".join(
        str(context.get(key) or "")
        for key in ("tenantId", "userId", "threadId", "messageId")
    ) + f"|{action_id}"
    if operation_key:
        identity += f"|{operation_key}"
    return "op-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]


def _assert_operation_scope(operation: OperationContext, context: dict[str, str]) -> None:
    """Prevent an opaque Operation ID from crossing an identity boundary."""

    checks = (
        ("operationId", operation.operation_id),
        ("tenantId", operation.tenant_id),
        ("userId", operation.user_id),
        ("threadId", operation.thread_id),
        ("originRunId", operation.origin_run_id),
        ("messageId", operation.message_id),
    )
    for key, expected in checks:
        actual = str(context.get(key) or "").strip()
        if actual and actual != str(expected or "").strip():
            raise PermissionError(
                "OPERATION_SCOPE_MISMATCH: Operation 不属于当前身份、Thread 或原始运行"
            )


@dataclass
class OperationRuntime:
    """Small stateful facade around one persisted Operation."""

    store: OperationStore
    operation: OperationContext
    _closed: bool = False

    @classmethod
    def start(
        cls,
        *,
        action_id: str,
        capability_id: str,
        payload: dict[str, Any],
        operation_key: str | None = None,
        required: bool | None = None,
    ) -> "OperationRuntime | None":
        context = current_agent_context()
        dsn = os.getenv("OA_AGENT_RUNTIME_POSTGRES_URI") or os.getenv("LANGGRAPH_POSTGRES_URI")
        must_run = _required_runtime() if required is None else required
        if not dsn:
            if must_run:
                raise RuntimeError("会议预约工作流需要配置 Agent Runtime PostgreSQL DSN")
            return None

        missing = _missing_context_fields(context)
        if missing:
            if must_run:
                raise AgentContextIncompleteError(missing)
            return None

        try:
            store = OperationStore(dsn)
        except Exception:
            if must_run:
                raise
            return None

        operation_id = _deterministic_operation_id(context, action_id, operation_key)
        try:
            operation = OperationContext(
                operation_id=operation_id,
                action_id=action_id,
                capability_id=capability_id,
                tenant_id=str(context.get("tenantId") or ""),
                user_id=str(context.get("userId") or ""),
                thread_id=str(context.get("threadId") or ""),
                origin_run_id=str(context.get("originRunId") or context.get("runId") or ""),
                current_run_id=str(context.get("runId") or ""),
                message_id=str(context.get("messageId") or ""),
                payload=payload,
            )
            operation = store.create_operation(operation)
        except Exception:
            store.close()
            if must_run:
                raise
            return None

        runtime = cls(store=store, operation=operation)
        set_operation_context(operation.operation_id)
        if operation.status == "CREATED":
            runtime.transition("COLLECTING_INFO", event_type="operation.collecting_info")
        return runtime

    @classmethod
    def open_existing(
        cls,
        operation_id: str,
        *,
        required: bool | None = None,
    ) -> "OperationRuntime | None":
        if not operation_id.strip():
            return None
        dsn = os.getenv("OA_AGENT_RUNTIME_POSTGRES_URI") or os.getenv("LANGGRAPH_POSTGRES_URI")
        must_run = _required_runtime() if required is None else required
        if not dsn:
            if must_run:
                raise RuntimeError("恢复 Operation 需要配置 Agent Runtime PostgreSQL DSN")
            return None
        store: OperationStore | None = None
        try:
            store = OperationStore(dsn)
            operation = store.get_operation(operation_id)
        except Exception:
            if store is not None:
                store.close()
            if must_run:
                raise
            return None
        if operation is None:
            store.close()
            if must_run:
                raise KeyError(f"Operation 不存在: {operation_id}")
            return None
        try:
            _assert_operation_scope(operation, current_agent_context())
        except PermissionError:
            store.close()
            raise
        runtime = cls(store=store, operation=operation)
        current_run_id = str(current_agent_context().get("runId") or "").strip()
        # A resume is a new Run of the same Operation. Persist that correlation
        # change in the same Runtime store so recovery queries do not rely on
        # whichever checkpoint happened to be loaded in memory.
        if current_run_id and current_run_id != "local-run" and current_run_id != operation.current_run_id:
            try:
                event = runtime._event(
                    "operation.resumed",
                    {
                        "fromRunId": operation.current_run_id,
                        "toRunId": current_run_id,
                    },
                    aggregate_version=operation.version + 1,
                )
                runtime.operation = store.patch_operation(
                    operation_id,
                    expected_version=operation.version,
                    current_run_id=current_run_id,
                    event=event,
                )
            except Exception:
                store.close()
                if must_run:
                    raise
                return None
        set_operation_context(runtime.operation.operation_id)
        return runtime

    @classmethod
    def find_by_binding(
        cls,
        *,
        action_id: str,
        statuses: set[str] | frozenset[str],
        required: bool = True,
    ) -> list[OperationContext]:
        """Recover Operations without relying on Redis task projections."""
        context = current_agent_context()
        dsn = os.getenv("OA_AGENT_RUNTIME_POSTGRES_URI") or os.getenv("LANGGRAPH_POSTGRES_URI")
        if not dsn:
            if required:
                raise RuntimeError("恢复 Operation 需要配置 Agent Runtime PostgreSQL DSN")
            return []
        store = OperationStore(dsn)
        try:
            return store.find_operations(
                action_id=action_id,
                statuses=statuses,
                tenant_id=str(context.get("tenantId") or ""),
                user_id=str(context.get("userId") or ""),
                thread_id=str(context.get("threadId") or ""),
                message_id=str(context.get("messageId") or ""),
                origin_run_id=str(context.get("originRunId") or context.get("runId") or ""),
            )
        finally:
            store.close()

    @classmethod
    def settle_approval(
        cls,
        operation_id: str,
        approval_status: str,
        *,
        approval_id: str | None = None,
        required: bool = True,
    ) -> OperationContext | None:
        """Reflect a Java-owned terminal Approval decision in the Operation.

        Approval is authoritative for the human decision, while Operation is
        authoritative for Agent orchestration.  The bridge is deliberately
        narrow: only a pending approval gate may be cancelled or expired.  A
        late or contradictory decision must not rewrite a running or already
        terminal operation silently.
        """

        normalized = str(approval_status or "").strip().upper()
        target = {
            "REJECTED": "CANCELLED",
            "EXPIRED": "EXPIRED",
        }.get(normalized)
        if target is None:
            return None

        runtime = cls.open_existing(operation_id, required=required)
        if runtime is None:
            return None
        try:
            current = runtime.operation.status
            if current == target:
                return runtime.operation
            if current == "WAITING_APPROVAL":
                return runtime.transition(
                    target,
                    event_type=(
                        "operation.approval_rejected"
                        if normalized == "REJECTED"
                        else "operation.approval_expired"
                    ),
                    data={
                        "approvalId": approval_id,
                        "approvalStatus": normalized,
                        "reason": "java_approval_terminal",
                    },
                )
            if current in {"SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"}:
                # A replayed approval read must be idempotent.  Do not attempt
                # to replace an already-recorded Operation terminal fact.
                return runtime.operation
            raise RuntimeError(
                f"Approval {normalized} 与 Operation 状态冲突: {current} -> {target}"
            )
        finally:
            runtime.close()

    @property
    def operation_id(self) -> str:
        return self.operation.operation_id

    def transition(
        self,
        status: OperationStatus,
        *,
        event_type: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> OperationContext:
        previous_status = self.operation.status
        event = self._event(
            event_type or "operation.status.changed",
            {"fromStatus": previous_status, "toStatus": status, **(data or {})},
            aggregate_version=self.operation.version + 1,
        )
        updated = self.store.transition_operation(
            self.operation_id,
            status,
            expected_version=self.operation.version,
            run_id=self._context().get("runId"),
            event=event,
        )
        self.operation = updated
        set_operation_context(updated.operation_id)
        return updated

    def patch_result(self, result: dict[str, Any], *, event_type: str = "operation.result.updated") -> OperationContext:
        # A replayed Effect/Operation result is a read, not a new fact.  Avoid
        # creating a version and outbox event when the durable result already
        # matches; this keeps resume idempotency meaningful across retries.
        if result == self.operation.result:
            return self.operation
        event = self._event(
            event_type,
            {"result": result},
            aggregate_version=self.operation.version + 1,
        )
        updated = self.store.patch_operation(
            self.operation_id,
            expected_version=self.operation.version,
            current_run_id=self._context().get("runId") or self.operation.current_run_id,
            result=result,
            event=event,
        )
        self.operation = updated
        return updated

    def merge_payload(
        self,
        patch: dict[str, Any],
        *,
        event_type: str = "operation.payload.updated",
    ) -> OperationContext:
        """Persist structured workflow facts on the Operation aggregate.

        Workflow facts are request-scoped input/progress, not a second task
        entity.  Keeping the merge behind the optimistic-locking Operation
        repository makes retries and resume use the same durable aggregate.
        """
        if not isinstance(patch, dict):
            raise TypeError("Operation payload patch must be an object")
        merged = {**self.operation.payload, **patch}
        if merged == self.operation.payload:
            return self.operation
        event = self._event(
            event_type,
            {"changedFields": sorted(str(key) for key in patch)},
            aggregate_version=self.operation.version + 1,
        )
        updated = self.store.patch_operation(
            self.operation_id,
            expected_version=self.operation.version,
            current_run_id=self._context().get("runId") or self.operation.current_run_id,
            payload=merged,
            event=event,
        )
        self.operation = updated
        set_operation_context(updated.operation_id)
        return updated

    def bind_approval(self, approval_id: str) -> OperationContext:
        if self.operation.approval_id == approval_id:
            return self.operation
        if self.operation.approval_id and self.operation.approval_id != approval_id:
            raise ValueError(
                f"Operation {self.operation_id} 已绑定其他 Approval: {self.operation.approval_id}"
            )
        event = self._event(
            "approval.bound",
            {"approvalId": approval_id},
            aggregate_version=self.operation.version + 1,
        )
        updated = self.store.bind_approval(
            self.operation_id,
            approval_id,
            expected_version=self.operation.version,
            event=event,
        )
        self.operation = updated
        return updated

    def create_effect(
        self,
        *,
        request_data: dict[str, Any],
        reconcile_strategy: str,
        idempotency_key: str | None = None,
    ) -> EffectRecord:
        serialized = json.dumps(request_data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        effect = EffectRecord(
            operation_id=self.operation_id,
            action_id=self.operation.action_id,
            idempotency_key=idempotency_key or f"{self.operation_id}:commit",
            request_hash=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
            reconcile_strategy=reconcile_strategy,
            request_data=request_data,
        )
        event = self._event(
            "effect.planned",
            {"effectId": effect.effect_id, "actionId": effect.action_id},
            aggregate_type="effect",
            aggregate_id=effect.effect_id,
            aggregate_version=effect.version,
        )
        saved = self.store.create_effect(effect, event=event)
        return saved

    def get_effect(self, idempotency_key: str) -> EffectRecord | None:
        """Load a previously planned effect for this Operation."""

        return self.store.get_effect_by_idempotency_key(
            self.operation_id,
            idempotency_key,
        )

    def claim_effect(self, effect: EffectRecord, *, lease_owner: str, lease_until: datetime) -> EffectRecord:
        event = self._event(
            "effect.claimed",
            {"effectId": effect.effect_id, "attempt": effect.attempt + 1},
            aggregate_type="effect",
            aggregate_id=effect.effect_id,
            aggregate_version=effect.version + 1,
        )
        claimed = self.store.claim_effect(
            effect.effect_id,
            lease_owner=lease_owner,
            lease_until=lease_until,
            expected_version=effect.version,
            event=event,
        )
        return claimed

    def transition_effect(
        self,
        effect: EffectRecord,
        status: EffectStatus,
        *,
        response_data: dict[str, Any] | None = None,
        error_data: dict[str, Any] | None = None,
    ) -> EffectRecord:
        event = self._event(
            f"effect.{status.lower()}",
            {"effectId": effect.effect_id, "response": response_data, "error": error_data},
            aggregate_type="effect",
            aggregate_id=effect.effect_id,
            aggregate_version=effect.version + 1,
        )
        updated = self.store.transition_effect(
            effect.effect_id,
            status,
            expected_version=effect.version,
            response_data=response_data,
            error_data=error_data,
            event=event,
        )
        return updated

    def record_outcome(self, outcome: dict[str, Any]) -> None:
        status = str(outcome.get("status") or "")
        if status == "CONFLICT_BLOCKED" and self.operation.status == "RUNNING":
            self.transition("READY", event_type="operation.ready", data={"reason": "conflict_blocked"})
        elif status == "FAILED" and self.operation.status not in {
            "SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"
        }:
            self.transition("FAILED", event_type="operation.failed")
        self.patch_result(outcome)

    def close(self) -> None:
        if not self._closed:
            self.store.close()
            self._closed = True

    def _context(self) -> dict[str, str]:
        return current_agent_context()

    def _event(
        self,
        event_type: str,
        data: dict[str, Any],
        *,
        aggregate_type: str = "operation",
        aggregate_id: str | None = None,
        aggregate_version: int | None = None,
    ) -> EventEnvelope:
        context = self._context()
        event = EventEnvelope(
            source="python-runtime",
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id or self.operation_id,
            aggregate_version=aggregate_version or self.operation.version,
            tenant_id=str(context.get("tenantId") or self.operation.tenant_id),
            user_id=str(context.get("userId") or self.operation.user_id),
            thread_id=str(context.get("threadId") or self.operation.thread_id),
            message_id=str(context.get("messageId") or self.operation.message_id),
            operation_id=self.operation_id,
            run_id=str(context.get("runId") or self.operation.current_run_id),
            # Operation is the cross-Run aggregate.  A resume changes runId,
            # but it must not split the durable event correlation chain.
            correlation_id=self.operation_id,
            data=data,
        )
        return event


def set_active_operation(runtime: OperationRuntime | None) -> Token[OperationRuntime | None]:
    return _ACTIVE_OPERATION.set(runtime)


def get_active_operation() -> OperationRuntime | None:
    return _ACTIVE_OPERATION.get()


def reset_active_operation(token: Token[OperationRuntime | None]) -> None:
    _ACTIVE_OPERATION.reset(token)


__all__ = [
    "action_id_for",
    "OperationRuntime",
    "get_active_operation",
    "reset_active_operation",
    "set_active_operation",
]
