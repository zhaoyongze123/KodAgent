"""代码拥有的跨领域步骤并发协调器。

文件职责
========
中央编译器负责生成已验证的 ``CoordinationBatch``，领域子 Agent 只负责执行各自
的 WorkOrder。本模块处于二者之间，依据步骤 DAG 决定哪些步骤可以同时运行，
并将每一次状态变化写入持久化存储和 Runtime Outbox。

它刻意不调用模型、不从自然语言猜动作，也不把一个领域的工具暴露给另一个领域。
因此并发只是一种执行策略，不会放宽既有 Action Catalog、WorkOrder、HITL 或
Operation/Effect 边界。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from ..domain.coordination import (
    CoordinationBatch,
    CoordinationStep,
    CoordinationStepStatus,
    batch_status_from_steps,
)
from ..domain.events import EventEnvelope
from ..persistence.operation_store import OperationStore


@dataclass(frozen=True)
class StepExecutionOutcome:
    """领域执行适配器提交给协调器的结构化结果。

    参数：
        status：只允许领域执行后的稳定步骤状态；协调器不接受 PENDING/RUNNING。
        receipt：真实 executor 回执，不接受子 Agent 的自由文本作为事实。
        operation_id：领域工作流实际创建/恢复的 Operation ID，可为空（纯查询）。
        error_code/error_message：失败时的结构化诊断。
    """

    status: CoordinationStepStatus
    receipt: dict[str, Any] | None = None
    operation_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"SUCCEEDED", "WAITING_APPROVAL", "FAILED", "CANCELLED"}:
            raise ValueError(f"领域执行器不能返回中间步骤状态: {self.status}")


class CoordinationStepExecutor(Protocol):
    """连接 DeepAgents 子图的受限适配器协议。"""

    def __call__(self, step: CoordinationStep) -> Awaitable[StepExecutionOutcome]: ...


def runnable_steps(batch: CoordinationBatch) -> tuple[CoordinationStep, ...]:
    """返回当前可并发执行的步骤，不修改任何持久化状态。

    只有所有依赖成功，或依赖已失败但其声明 ``CONTINUE`` 时，步骤才可执行。被
    ``BLOCK_DEPENDENTS`` 失败步骤阻断的后继由 ``blocked_steps`` 标记为 SKIPPED。
    """

    by_id = {step.step_id: step for step in batch.steps}
    ready: list[CoordinationStep] = []
    for step in batch.steps:
        if step.status != "PENDING":
            continue
        dependencies = [by_id[dependency] for dependency in step.depends_on]
        if not dependencies:
            ready.append(step)
            continue
        if all(dependency.status == "SUCCEEDED" for dependency in dependencies):
            ready.append(step)
            continue
        # 失败但允许继续的依赖已经终态，因此不必等待；仍在执行/等待确认的依赖
        # 不能被越过。
        if all(
            dependency.status in {"SUCCEEDED", "FAILED", "SKIPPED", "CANCELLED"}
            and (dependency.status == "SUCCEEDED" or dependency.failure_policy == "CONTINUE")
            for dependency in dependencies
        ):
            ready.append(step)
    return tuple(ready)


def blocked_steps(batch: CoordinationBatch) -> tuple[CoordinationStep, ...]:
    """返回应被确定性跳过的 PENDING 后继步骤。"""

    by_id = {step.step_id: step for step in batch.steps}
    blocked: list[CoordinationStep] = []
    for step in batch.steps:
        if step.status != "PENDING":
            continue
        if any(
            by_id[dependency].status in {"FAILED", "SKIPPED", "CANCELLED"}
            and by_id[dependency].failure_policy == "BLOCK_DEPENDENTS"
            for dependency in step.depends_on
        ):
            blocked.append(step)
    return tuple(blocked)


class CoordinationRunner:
    """执行一个已创建批次的可运行步骤，支持重启后续跑。"""

    def __init__(self, store: OperationStore, executor: CoordinationStepExecutor) -> None:
        self._store = store
        self._executor = executor

    @staticmethod
    def _event(batch: CoordinationBatch, event_type: str, step: CoordinationStep | None = None, **data: Any) -> EventEnvelope:
        """构造不包含用户原文或业务敏感字段的运行统计事件。"""

        aggregate_type = "coordination_step" if step is not None else "coordination_batch"
        aggregate_id = f"{batch.batch_id}:{step.step_id}" if step is not None else batch.batch_id
        aggregate_version = (step.version + 1) if step is not None else (batch.version + 1)
        return EventEnvelope(
            source="coordination",
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            tenant_id=batch.tenant_id,
            user_id=batch.user_id,
            thread_id=batch.thread_id,
            message_id=batch.message_id,
            run_id=batch.current_run_id,
            correlation_id=batch.batch_id,
            data={
                "batchId": batch.batch_id,
                **({
                    "stepId": step.step_id,
                    "domain": step.domain,
                    "actionId": step.action_id,
                    "executor": step.executor_tool,
                } if step else {}),
                **data,
            },
        )

    async def run_ready(self, batch_id: str) -> CoordinationBatch:
        """执行当前可运行层并汇总状态。

        调用一次只运行当前依赖层：这使 WAITING_APPROVAL 能自然暂停，恢复后再次
        调用即可继续后继步骤；同一层通过 ``asyncio.gather`` 并行执行。
        """

        batch = self._store.get_coordination_batch(batch_id, required=True)
        assert batch is not None
        if batch.status == "CREATED":
            batch = self._store.transition_coordination_batch(
                batch.batch_id, "RUNNING", expected_version=batch.version,
                event=self._event(batch, "coordination.batch.started"),
            )
        if batch.status in {"SUCCEEDED", "FAILED", "CANCELLED", "PARTIAL_SUCCEEDED"}:
            return batch

        # 先清理被失败依赖确定性阻断的步骤，不能让它们永远停在 PENDING。
        for step in blocked_steps(batch):
            batch = self._store.transition_coordination_step(
                batch.batch_id, step.step_id, "SKIPPED",
                error_code="DEPENDENCY_FAILED",
                error_message="依赖步骤失败，当前步骤未执行。",
                event=self._event(batch, "coordination.step.skipped", step, reason="dependency_failed"),
            )

        ready = runnable_steps(batch)
        if ready:
            # 先持久化 RUNNING，再创建协程。服务在此后重启时可由恢复任务识别
            # 为未完成步骤，而不会重复写入终态事实。
            for step in ready:
                batch = self._store.transition_coordination_step(
                    batch.batch_id, step.step_id, "RUNNING",
                    event=self._event(batch, "coordination.step.started", step),
                )
            running = {step.step_id: next(item for item in batch.steps if item.step_id == step.step_id) for step in ready}
            outcomes = await asyncio.gather(
                *(self._run_one(step) for step in running.values()),
                return_exceptions=True,
            )
            for step, outcome in zip(running.values(), outcomes, strict=True):
                if isinstance(outcome, Exception):
                    batch = self._store.transition_coordination_step(
                        batch.batch_id, step.step_id, "FAILED",
                        error_code="COORDINATION_EXECUTOR_EXCEPTION",
                        error_message=f"{type(outcome).__name__}: {str(outcome)[:800]}",
                        event=self._event(batch, "coordination.step.failed", step, errorCode="COORDINATION_EXECUTOR_EXCEPTION"),
                    )
                    continue
                batch = self._store.transition_coordination_step(
                    batch.batch_id, step.step_id, outcome.status,
                    receipt=outcome.receipt, operation_id=outcome.operation_id,
                    error_code=outcome.error_code, error_message=outcome.error_message,
                    event=self._event(
                        batch,
                        "coordination.step.waiting_approval" if outcome.status == "WAITING_APPROVAL"
                        else "coordination.step.completed" if outcome.status == "SUCCEEDED"
                        else "coordination.step.failed",
                        step,
                        status=outcome.status,
                        errorCode=outcome.error_code,
                    ),
                )

        desired = batch_status_from_steps(batch.steps)
        if desired != batch.status:
            batch = self._store.transition_coordination_batch(
                batch.batch_id, desired, expected_version=batch.version,
                event=self._event(batch, f"coordination.batch.{desired.lower()}", status=desired),
            )
        return batch

    async def _run_one(self, step: CoordinationStep) -> StepExecutionOutcome:
        """隔离一个领域适配器异常，防止同批其他并行步骤被取消。"""

        return await self._executor(step)


__all__ = [
    "CoordinationRunner", "CoordinationStepExecutor", "StepExecutionOutcome",
    "blocked_steps", "runnable_steps",
]
