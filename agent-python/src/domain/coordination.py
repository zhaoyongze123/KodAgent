"""跨领域协作批次的持久化状态模型。

文件职责
========
一个 ``Operation`` 只表示一个领域中的一项业务动作，例如“创建个人日程草稿”。
当用户一次提出“查日程、查会议室并汇总”时，不能把多项动作塞进同一个
Operation，否则原有的幂等键、审批绑定和 HITL 状态会失去唯一含义。

本文件因此定义高一层的协作批次：

``CoordinationBatch``：一次用户请求的跨领域编排事实；
``CoordinationStep``：批次中的一个不可变领域 WorkOrder；

批次只负责依赖、并发、汇总与恢复。每个步骤的业务执行、正式事实和写入边界
仍由其所属领域的 WorkOrder / Operation / Effect 负责。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


CoordinationBatchStatus = Literal[
    "CREATED", "RUNNING", "WAITING_APPROVAL", "PARTIAL_SUCCEEDED",
    "SUCCEEDED", "FAILED", "CANCELLED",
]
CoordinationStepStatus = Literal[
    "PENDING", "RUNNING", "WAITING_APPROVAL", "SUCCEEDED", "FAILED",
    "SKIPPED", "CANCELLED",
]
StepFailurePolicy = Literal["CONTINUE", "BLOCK_DEPENDENTS"]

TERMINAL_BATCH_STATUSES = frozenset({"PARTIAL_SUCCEEDED", "SUCCEEDED", "FAILED", "CANCELLED"})
TERMINAL_STEP_STATUSES = frozenset({"SUCCEEDED", "FAILED", "SKIPPED", "CANCELLED"})


class CoordinationTransitionError(ValueError):
    """协作批次或步骤的版本、状态、依赖关系不合法。"""


class CoordinationStep(BaseModel):
    """一个可独立委派给领域子 Agent 的步骤。

    参数：
        step_id：批次内稳定唯一 ID，供依赖、回执和审计关联使用。
        work_order：中央编译后不可变的 WorkOrder JSON；子 Agent 仍只相信它。
        depends_on：必须先终态成功的步骤 ID 列表。
        failure_policy：当前步骤失败时是否阻断依赖它的后续步骤。
        operation_id：领域工作流创建后回填的 Operation ID，不预先伪造。
    """

    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1, max_length=128)
    domain: str = Field(min_length=1, max_length=64)
    action_id: str = Field(min_length=1, max_length=128)
    executor_tool: str = Field(min_length=1, max_length=128)
    work_order: dict[str, Any] = Field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    failure_policy: StepFailurePolicy = "BLOCK_DEPENDENTS"
    status: CoordinationStepStatus = "PENDING"
    version: int = Field(default=1, ge=1)
    operation_id: str | None = Field(default=None, max_length=128)
    receipt: dict[str, Any] | None = None
    error_code: str | None = Field(default=None, max_length=128)
    error_message: str | None = Field(default=None, max_length=1000)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @field_validator("depends_on")
    @classmethod
    def _unique_dependencies(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("depends_on 不能包含重复步骤")
        return value


class CoordinationBatch(BaseModel):
    """一次多领域请求的可恢复、版本化编排事实。"""

    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(default_factory=lambda: f"batch-{uuid4().hex[:20]}", min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=64)
    user_id: str = Field(min_length=1, max_length=64)
    thread_id: str = Field(min_length=1, max_length=128)
    origin_run_id: str = Field(min_length=1, max_length=128)
    current_run_id: str = Field(min_length=1, max_length=128)
    message_id: str = Field(min_length=1, max_length=128)
    request_summary: str | None = Field(default=None, max_length=1000)
    status: CoordinationBatchStatus = "CREATED"
    version: int = Field(default=1, ge=1)
    steps: tuple[CoordinationStep, ...] = Field(min_length=1, max_length=12)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("steps")
    @classmethod
    def _validate_step_graph(cls, steps: tuple[CoordinationStep, ...]) -> tuple[CoordinationStep, ...]:
        step_ids = [step.step_id for step in steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("协作批次的 step_id 必须唯一")
        known = set(step_ids)
        for step in steps:
            if step.step_id in step.depends_on:
                raise ValueError(f"步骤不能依赖自身: {step.step_id}")
            unknown = set(step.depends_on) - known
            if unknown:
                raise ValueError(f"步骤 {step.step_id} 引用了不存在的依赖: {sorted(unknown)}")
        # DFS 检测环；并发只在有向无环图中才有明确语义。
        dependencies = {step.step_id: set(step.depends_on) for step in steps}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise ValueError("协作步骤依赖图不能有环")
            if step_id in visited:
                return
            visiting.add(step_id)
            for parent in dependencies[step_id]:
                visit(parent)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in dependencies:
            visit(step_id)
        return steps


def transition_batch(
    batch: CoordinationBatch,
    target: CoordinationBatchStatus,
    *,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> CoordinationBatch:
    """校验后返回新的批次状态版本。"""

    if expected_version is not None and batch.version != expected_version:
        raise CoordinationTransitionError(
            f"CoordinationBatch 版本冲突: expected={expected_version}, actual={batch.version}"
        )
    allowed: dict[str, frozenset[str]] = {
        "CREATED": frozenset({"RUNNING", "CANCELLED", "FAILED"}),
        "RUNNING": frozenset({"WAITING_APPROVAL", "PARTIAL_SUCCEEDED", "SUCCEEDED", "FAILED", "CANCELLED"}),
        "WAITING_APPROVAL": frozenset({"RUNNING", "PARTIAL_SUCCEEDED", "SUCCEEDED", "FAILED", "CANCELLED"}),
        "PARTIAL_SUCCEEDED": frozenset(), "SUCCEEDED": frozenset(),
        "FAILED": frozenset(), "CANCELLED": frozenset(),
    }
    if target not in allowed[batch.status]:
        raise CoordinationTransitionError(f"非法批次状态迁移: {batch.status} -> {target}")
    return batch.model_copy(update={
        "status": target,
        "version": batch.version + 1,
        "updated_at": now or datetime.now(timezone.utc),
    })


def transition_step(
    step: CoordinationStep,
    target: CoordinationStepStatus,
    *,
    now: datetime | None = None,
    receipt: dict[str, Any] | None = None,
    operation_id: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> CoordinationStep:
    """校验步骤生命周期，并只在终态写入完成时间。"""

    allowed: dict[str, frozenset[str]] = {
        "PENDING": frozenset({"RUNNING", "SKIPPED", "CANCELLED"}),
        "RUNNING": frozenset({"WAITING_APPROVAL", "SUCCEEDED", "FAILED", "CANCELLED"}),
        "WAITING_APPROVAL": frozenset({"SUCCEEDED", "FAILED", "CANCELLED"}),
        "SUCCEEDED": frozenset(), "FAILED": frozenset(), "SKIPPED": frozenset(), "CANCELLED": frozenset(),
    }
    if target not in allowed[step.status]:
        raise CoordinationTransitionError(f"非法协作步骤状态迁移: {step.status} -> {target}")
    timestamp = now or datetime.now(timezone.utc)
    updates: dict[str, Any] = {"status": target, "version": step.version + 1}
    if target == "RUNNING":
        updates["started_at"] = step.started_at or timestamp
    if target in TERMINAL_STEP_STATUSES:
        updates["completed_at"] = timestamp
    if receipt is not None:
        updates["receipt"] = receipt
    if operation_id is not None:
        updates["operation_id"] = operation_id
    if error_code is not None:
        updates["error_code"] = error_code
    if error_message is not None:
        updates["error_message"] = error_message
    return step.model_copy(update=updates)


def batch_status_from_steps(steps: tuple[CoordinationStep, ...]) -> CoordinationBatchStatus:
    """根据步骤事实计算批次终态，避免由模型主观总结成功与否。"""

    statuses = {step.status for step in steps}
    if "WAITING_APPROVAL" in statuses:
        return "WAITING_APPROVAL"
    if statuses & {"PENDING", "RUNNING"}:
        return "RUNNING"
    succeeded = sum(status == "SUCCEEDED" for status in statuses)
    failed = bool(statuses & {"FAILED", "SKIPPED", "CANCELLED"})
    if succeeded and failed:
        return "PARTIAL_SUCCEEDED"
    if succeeded:
        return "SUCCEEDED"
    return "CANCELLED" if statuses == {"CANCELLED"} else "FAILED"


__all__ = [
    "CoordinationBatch", "CoordinationBatchStatus", "CoordinationStep",
    "CoordinationStepStatus", "CoordinationTransitionError", "StepFailurePolicy",
    "TERMINAL_BATCH_STATUSES", "TERMINAL_STEP_STATUSES", "batch_status_from_steps",
    "transition_batch", "transition_step",
]
