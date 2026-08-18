"""Domain-neutral coordination for one approval-backed external effect.

The coordinator deliberately knows nothing about meetings, schedules or Java
payload fields.  A domain adapter supplies an Action ID, an idempotency key,
the request data and a resolver for an UNKNOWN result.  This keeps the stable
Operation/Effect protocol in one place while leaving business semantics at
the domain boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from ..domain.effect import EffectRecord
from .operation_runtime import OperationRuntime


class CommitKernelError(RuntimeError):
    """The durable runtime rejected the requested effect execution."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class CommitInProgress(RuntimeError):
    """Another worker owns the current external side-effect lease."""


class ReconciliationPending(RuntimeError):
    """The external result is still unknown and must not be retried blindly."""


class StoredFinalFailure(RuntimeError):
    """An earlier attempt already reached a final business failure."""

    def __init__(self, error_data: Mapping[str, Any] | None):
        self.error_data = dict(error_data or {})
        self.code = str(self.error_data.get("code") or "EFFECT_FAILED_FINAL")
        self.message = str(self.error_data.get("message") or "业务操作未被接受")
        super().__init__(self.message)


@dataclass
class CommitStart:
    """Result of preparing an effect for execution or reconciliation."""

    runtime: OperationRuntime
    effect: EffectRecord
    recovered_result: dict[str, Any] | None = None
    reconciliation_required: bool = False
    settled: bool = False


class EffectCommitCoordinator:
    """Coordinate one idempotent Effect without domain branching."""

    def __init__(
        self,
        *,
        runtime: OperationRuntime,
        expected_action_id: str,
        request_data: dict[str, Any],
        idempotency_key: str,
        reconcile_strategy: str,
        lease_owner: str,
        lease_seconds: int = 60,
        result_field: str = "result",
    ) -> None:
        self.runtime = runtime
        self.expected_action_id = expected_action_id
        self.request_data = request_data
        self.idempotency_key = idempotency_key
        self.reconcile_strategy = reconcile_strategy
        self.lease_owner = lease_owner[:128]
        self.lease_seconds = lease_seconds
        self.result_field = result_field
        self.effect: EffectRecord | None = None

    def prepare(self) -> CommitStart:
        """Create or recover the Effect, then claim executable work."""

        if self.runtime.operation.action_id != self.expected_action_id:
            raise CommitKernelError(
                "OPERATION_ACTION_MISMATCH",
                f"Operation actionId 不匹配，期望 {self.expected_action_id}",
            )

        effect = self.runtime.get_effect(self.idempotency_key)
        if effect is None:
            self._transition_to_committing()
            effect = self.runtime.create_effect(
                request_data=self.request_data,
                reconcile_strategy=self.reconcile_strategy,
                idempotency_key=self.idempotency_key,
            )
        elif self.runtime.operation.status == "WAITING_APPROVAL":
            self._transition_to_committing()
        self.effect = effect

        if effect.status == "SUCCEEDED":
            result = dict(effect.response_data or {})
            self.settle_success(result)
            return CommitStart(
                runtime=self.runtime,
                effect=effect,
                recovered_result=result,
                settled=True,
            )
        if effect.status == "FAILED_FINAL":
            raise StoredFinalFailure(effect.error_data)
        if effect.status in {"UNKNOWN", "RECONCILING"}:
            return CommitStart(
                runtime=self.runtime,
                effect=effect,
                reconciliation_required=True,
            )
        if self.runtime.operation.status == "UNKNOWN":
            raise ReconciliationPending("提交结果仍未知，请先完成结果核对")
        if effect.status in {"CLAIMED", "EXECUTING"}:
            raise CommitInProgress("提交正在由其他执行者处理")
        if effect.status not in {"PLANNED", "FAILED_RETRYABLE"}:
            raise CommitKernelError(
                "EFFECT_STATE_INVALID",
                f"Effect 当前状态 {effect.status} 不能执行",
            )

        claimed = self.runtime.claim_effect(
            effect,
            lease_owner=self.lease_owner,
            lease_until=datetime.now(timezone.utc) + timedelta(seconds=self.lease_seconds),
        )
        executing = self.runtime.transition_effect(claimed, "EXECUTING")
        self.effect = executing
        return CommitStart(runtime=self.runtime, effect=executing)

    def reconcile(
        self,
        resolver: Callable[[EffectRecord], Mapping[str, Any] | None],
        *,
        pending_message: str = "提交结果仍在核对中，请稍后重试",
    ) -> dict[str, Any]:
        """Resolve UNKNOWN through a domain-owned read-only result query."""

        effect = self.effect
        if effect is None:
            raise CommitKernelError("EFFECT_NOT_PREPARED", "Effect 尚未准备")
        if effect.status == "UNKNOWN":
            effect = self.runtime.transition_effect(effect, "RECONCILING")
            self.effect = effect
        try:
            resolved = resolver(effect)
        except StoredFinalFailure as exc:
            # A read-side reconciler can establish a deterministic business
            # failure (for example, the target task was completed with the
            # opposite action). That is no longer an UNKNOWN transport
            # outcome; persist the terminal Effect/Operation state before
            # returning the error to the domain adapter.
            self.record_failure(exc, unknown=False, code=exc.code)
            raise
        except Exception as exc:
            self._leave_unknown(effect, {"code": "RECONCILE_UNAVAILABLE", "message": str(exc)})
            raise ReconciliationPending(pending_message) from exc
        if not isinstance(resolved, Mapping):
            self._leave_unknown(effect, {
                "code": "RECONCILE_PENDING",
                "message": pending_message,
            })
            raise ReconciliationPending(pending_message)
        result = dict(resolved)
        self.settle_success(result)
        return result

    def settle_success(self, result: Mapping[str, Any]) -> EffectRecord:
        """Record the external success and close the Operation exactly once."""

        effect = self.effect
        if effect is None:
            raise CommitKernelError("EFFECT_NOT_PREPARED", "Effect 尚未准备")
        if effect.status != "SUCCEEDED":
            # A successful reconciliation closes the previous UNKNOWN/failure
            # evidence.  Keeping stale error_data on a terminal success makes
            # audit consumers report a false active fault.
            effect = self.runtime.transition_effect(
                effect, "SUCCEEDED", response_data=dict(result), error_data={}
            )
            self.effect = effect
        if self.runtime.operation.status == "WAITING_APPROVAL":
            self.runtime.transition("COMMITTING", event_type="operation.committing")
        if self.runtime.operation.status in {"COMMITTING", "UNKNOWN"}:
            self.runtime.transition("SUCCEEDED", event_type="operation.succeeded")
        elif self.runtime.operation.status != "SUCCEEDED":
            raise CommitKernelError(
                "OPERATION_STATE_INVALID",
                f"Effect 已成功但 Operation 当前状态为 {self.runtime.operation.status}",
            )
        self.runtime.patch_result({
            "status": "SUCCEEDED",
            "effectId": effect.effect_id,
            self.result_field: dict(result),
        })
        return effect

    def record_failure(
        self,
        exc: Exception,
        *,
        unknown: bool,
        code: str,
    ) -> None:
        """Persist a final or ambiguous failure without swallowing state errors."""

        error_data = {
            "code": code,
            "message": str(exc)[:1000],
            "kind": "unknown" if unknown else "business",
            "retryable": unknown,
            "errorType": type(exc).__name__,
        }
        effect = self.effect
        if effect is not None and effect.status in {"PLANNED", "CLAIMED", "EXECUTING", "RECONCILING"}:
            effect = self.runtime.transition_effect(
                effect,
                "UNKNOWN" if unknown else "FAILED_FINAL",
                error_data=error_data,
            )
            self.effect = effect
        target = "UNKNOWN" if unknown else "FAILED"
        if self.runtime.operation.status in {"COMMITTING", "UNKNOWN"}:
            self.runtime.transition(
                target,
                event_type="operation.unknown" if unknown else "operation.failed",
                data={"effectId": effect.effect_id if effect else None, "error": error_data},
            )
        self.runtime.patch_result({
            "status": target,
            "effectId": effect.effect_id if effect else None,
            "error": error_data,
        })

    def _transition_to_committing(self) -> None:
        status = self.runtime.operation.status
        if status == "WAITING_APPROVAL":
            self.runtime.transition("COMMITTING", event_type="operation.committing")
        elif status not in {"COMMITTING", "UNKNOWN"}:
            raise CommitKernelError(
                "OPERATION_STATE_INVALID",
                f"Operation 当前状态 {status} 不能提交外部副作用",
            )

    def _leave_unknown(self, effect: EffectRecord, error_data: dict[str, Any]) -> None:
        current = self.effect or effect
        if current.status == "RECONCILING":
            self.effect = self.runtime.transition_effect(current, "UNKNOWN", error_data=error_data)


__all__ = [
    "CommitInProgress",
    "CommitKernelError",
    "CommitStart",
    "EffectCommitCoordinator",
    "ReconciliationPending",
    "StoredFinalFailure",
]
