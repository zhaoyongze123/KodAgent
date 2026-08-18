"""跨领域批次在主图与领域子图之间的确定性派发桥。

文件职责
========
``CoordinationBatch`` 已经由中央编译器持久化，每个步骤都带有不可变
``WorkOrder``。本模块不理解用户自然语言，也不调用业务工具；它只负责：

* 将当前可运行的步骤转换为 DeepAgents ``task`` 调用的受控描述；
* 在父图收到子 Agent 的结构化回执后，更新对应步骤与批次状态；
* 为主 Agent 的最终汇总提供脱敏的状态摘要。

因此模型不能构造批次 ID、步骤 ID、子 Agent 名称或 WorkOrder。任务并行由
DeepAgents 同一条 AIMessage 内的多个 ``task`` 调用实现；数据库中的批次状态
则始终是恢复、审计和最终汇总的唯一事实源。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .delegated_receipt import (
    parse_approval_draft_receipt,
    parse_execution_receipt,
    parse_meeting_draft_receipt,
    parse_party_file_draft_receipt,
    parse_personal_schedule_draft_receipt,
    parse_project_investigation_receipt,
)
from .capabilities import action_read_only, resolve_action
from .domain_dispatch import WorkOrder, parse_work_order, serialize_work_order
from .execution_contracts import contract_for_executor
from ..domain.coordination import CoordinationBatch, CoordinationStep, batch_status_from_steps
from ..domain.events import EventEnvelope
from ..persistence.operation_store import OperationStore
from ..tools.common.events import current_agent_context


COORDINATION_MARKER = "KODAGENT_COORDINATION="


@dataclass(frozen=True)
class CoordinationTask:
    """一项由主图代码签发的领域子 Agent 委派。

    参数：
        batch_id：持久化批次 ID，不由模型提供。
        step_id：批次内步骤 ID，不由模型提供。
        subagent_type：执行器契约声明的唯一领域子 Agent。
        description：传给 DeepAgents task 的 WorkOrder 和关联标记。
    """

    batch_id: str
    step_id: str
    subagent_type: str
    description: str


def _event(
    batch: CoordinationBatch,
    event_type: str,
    *,
    step: CoordinationStep | None = None,
    **data: Any,
) -> EventEnvelope:
    """构造可审计但不携带用户原文、WorkOrder 或业务结果的批次事件。"""

    return EventEnvelope(
        source="coordination",
        event_type=event_type,
        aggregate_type="coordination_step" if step is not None else "coordination_batch",
        aggregate_id=f"{batch.batch_id}:{step.step_id}" if step is not None else batch.batch_id,
        aggregate_version=(step.version + 1) if step is not None else (batch.version + 1),
        tenant_id=batch.tenant_id,
        user_id=batch.user_id,
        thread_id=batch.thread_id,
        message_id=batch.message_id,
        run_id=batch.current_run_id,
        correlation_id=batch.batch_id,
        data={
            "batchId": batch.batch_id,
            **({"stepId": step.step_id, "domain": step.domain, "actionId": step.action_id} if step else {}),
            **data,
        },
    )


def _step_owner(step: CoordinationStep) -> str | None:
    """从已验证 executor 契约解析唯一领域子 Agent。"""

    contract = contract_for_executor(step.executor_tool)
    if contract is None or not contract.is_available():
        return None
    return contract.owner_agent


def _task_description(batch_id: str, step: CoordinationStep) -> str:
    """在 WorkOrder 后附加父图专用关联标记，子 Agent 不解释该标记。"""

    work_order = WorkOrder.model_validate(step.work_order)
    marker = json.dumps(
        {"batchId": batch_id, "stepId": step.step_id},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"{serialize_work_order(work_order)}\n{COORDINATION_MARKER}{marker}"


def task_from_description(description: str) -> tuple[str, str, WorkOrder] | None:
    """读取代码签发标记并复验 WorkOrder，解析失败一律不派发。"""

    work_order = parse_work_order(description)
    marker_text = str(description or "").split(COORDINATION_MARKER, 1)
    if work_order is None or len(marker_text) != 2:
        return None
    try:
        marker = json.loads(marker_text[1].splitlines()[0])
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(marker, dict):
        return None
    batch_id = str(marker.get("batchId") or "").strip()
    step_id = str(marker.get("stepId") or "").strip()
    return (batch_id, step_id, work_order) if batch_id and step_id else None


def _scope_matches(batch: CoordinationBatch) -> bool:
    """批次只能由签发它的用户和 Thread 在当前运行中派发。"""

    context = current_agent_context()
    return (
        batch.tenant_id == str(context.get("tenantId") or "")
        and batch.user_id == str(context.get("userId") or "")
        and batch.thread_id == str(context.get("threadId") or "")
    )


def load_tasks(batch_id: str) -> tuple[CoordinationTask, ...]:
    """读取一个已创建批次并返回当前可派发步骤。

    该函数只接受路由工具已经落库的 ``batch_id``。它不会根据主模型输出重新创建
    步骤，也不会复跑 ``WAITING_APPROVAL`` 或已终态步骤。
    """

    store = OperationStore()
    try:
        batch = store.get_coordination_batch(batch_id, required=True)
    finally:
        store.close()
    assert batch is not None
    if not _scope_matches(batch):
        raise PermissionError("协作批次不属于当前用户或对话")
    if batch.status not in {"CREATED", "RUNNING"}:
        return ()
    tasks: list[tuple[bool, CoordinationTask]] = []
    for step in batch.steps:
        if step.status != "PENDING" or step.depends_on:
            # 第一阶段编译器不允许依赖。保留判断能让历史/未来 DAG 数据在没有
            # 显式恢复器前不被错误并行派发。
            continue
        owner = _step_owner(step)
        if owner is None:
            raise RuntimeError(f"步骤 {step.step_id} 的执行器当前不可用")
        action = resolve_action(step.domain, step.action_id)
        # 同批次只允许一个写草稿步骤。将其排在只读步骤之后，使父图在同一轮
        # 收到 task 结果时仍能由现有 HITL 投影准确识别最后一项草稿回执；执行
        # 仍由 ToolNode 并发，不把这个展示/投影顺序当成数据依赖。
        tasks.append((
            bool(action is not None and action_read_only(action)),
            CoordinationTask(
            batch_id=batch.batch_id,
            step_id=step.step_id,
            subagent_type=owner,
            description=_task_description(batch.batch_id, step),
            ),
        ))
    return tuple(task for _, task in sorted(tasks, key=lambda item: (not item[0], item[1].step_id)))


def start_tasks(batch_id: str, tasks: tuple[CoordinationTask, ...]) -> None:
    """先将准备派发的步骤持久化为 RUNNING，再让父图执行 task。

    进程在 task 返回前重启时，这些步骤不会被当成 PENDING 重复派发；恢复器应把
    RUNNING 作为需要人工/确定性核对的中间状态，而不是直接重放写操作。
    """

    if not tasks:
        return
    store = OperationStore()
    try:
        batch = store.get_coordination_batch(batch_id, required=True)
        assert batch is not None
        if not _scope_matches(batch):
            raise PermissionError("协作批次不属于当前用户或对话")
        if batch.status == "CREATED":
            batch = store.transition_coordination_batch(
                batch.batch_id, "RUNNING", expected_version=batch.version,
                event=_event(batch, "coordination.batch.started"),
            )
        wanted = {task.step_id for task in tasks}
        for step in batch.steps:
            if step.step_id in wanted and step.status == "PENDING":
                batch = store.transition_coordination_step(
                    batch.batch_id, step.step_id, "RUNNING",
                    event=_event(batch, "coordination.step.started", step),
                )
    finally:
        store.close()


def _receipt_outcome(step: CoordinationStep, content: Any) -> tuple[str, dict[str, Any] | None, str | None, str | None, str | None]:
    """把受限 task 回执归一化为步骤状态，不从子 Agent 自由文本推断结果。"""

    execution = parse_execution_receipt(content)
    if execution is not None:
        if execution.plan_id != str(step.work_order.get("planId") or "") or execution.executor_tool != step.executor_tool:
            return ("FAILED", None, None, "RECEIPT_MISMATCH", "子 Agent 回执与当前步骤契约不匹配。")
        receipt = execution.model_dump(by_alias=True, exclude_none=True)
        if execution.status == "SUCCEEDED":
            return ("SUCCEEDED", receipt, None, None, None)
        return ("FAILED", receipt, None, execution.error_code or "EXECUTOR_FAILED", execution.message or "领域执行未成功。")

    project = parse_project_investigation_receipt(content)
    if project is not None:
        if (
            step.domain != "project"
            or step.action_id != "project.investigate"
            or project.plan_id != str(step.work_order.get("planId") or "")
        ):
            return ("FAILED", None, None, "PROJECT_RECEIPT_MISMATCH", "项目调查回执与当前步骤契约不匹配。")
        receipt = project.model_dump(by_alias=True, exclude_none=True)
        if project.status == "SUCCEEDED":
            return ("SUCCEEDED", receipt, None, None, None)
        return ("FAILED", receipt, None, "PROJECT_INVESTIGATION_FAILED", "项目调查未取得可用事实。")

    parsers = (
        parse_meeting_draft_receipt,
        parse_personal_schedule_draft_receipt,
        parse_party_file_draft_receipt,
        parse_approval_draft_receipt,
    )
    for parser in parsers:
        receipt = parser(content)
        if receipt is None:
            continue
        if receipt.domain != step.domain:
            return ("FAILED", None, None, "DRAFT_RECEIPT_DOMAIN_MISMATCH", "草稿回执与当前领域不匹配。")
        data = receipt.model_dump(by_alias=True, exclude_none=True)
        return ("WAITING_APPROVAL", data, receipt.operation_id, None, None)
    return ("FAILED", None, None, "MISSING_EXECUTION_RECEIPT", "领域子 Agent 未返回可验证的执行回执。")


def record_task_result(description: str, content: Any) -> CoordinationBatch | None:
    """将一个父图 task 结果写回对应步骤；重复读取不改变终态步骤。"""

    parsed = task_from_description(description)
    if parsed is None:
        return None
    batch_id, step_id, work_order = parsed
    store = OperationStore()
    try:
        batch = store.get_coordination_batch(batch_id, required=True)
        assert batch is not None
        if not _scope_matches(batch):
            raise PermissionError("协作批次不属于当前用户或对话")
        step = next((item for item in batch.steps if item.step_id == step_id), None)
        if step is None or step.status != "RUNNING":
            return batch
        # 关联标记、数据库步骤、WorkOrder 三者必须一致。任一处被污染都不采纳。
        if (
            work_order.plan_id != str(step.work_order.get("planId") or "")
            or work_order.execution_tool != step.executor_tool
            or work_order.domain != step.domain
        ):
            return store.transition_coordination_step(
                batch_id, step_id, "FAILED", error_code="WORK_ORDER_MISMATCH",
                error_message="派发 WorkOrder 与持久化步骤不一致。",
                event=_event(batch, "coordination.step.failed", step, errorCode="WORK_ORDER_MISMATCH"),
            )
        status, receipt, operation_id, code, message = _receipt_outcome(step, content)
        batch = store.transition_coordination_step(
            batch_id, step_id, status, receipt=receipt, operation_id=operation_id,
            error_code=code, error_message=message,
            event=_event(
                batch,
                "coordination.step.waiting_approval" if status == "WAITING_APPROVAL"
                else "coordination.step.completed" if status == "SUCCEEDED"
                else "coordination.step.failed",
                step,
                status=status,
                errorCode=code,
            ),
        )
        desired = batch_status_from_steps(batch.steps)
        if desired != batch.status:
            batch = store.transition_coordination_batch(
                batch.batch_id, desired, expected_version=batch.version,
                event=_event(batch, f"coordination.batch.{desired.lower()}", status=desired),
            )
        return batch
    finally:
        store.close()


def sync_operation_completion(operation_id: str) -> tuple[CoordinationBatch, ...]:
    """将已完成的领域 Operation 回收为其协作步骤的终态。

    HITL 卡片的确认仍由原确认工具和 Java/Effect 链路完成。本函数只在确认工具
    已经返回后读取 Python Operation 的终态，再把对应的 ``WAITING_APPROVAL``
    步骤更新为成功、失败或取消；绝不主动提交或重复执行任何业务写入。
    """

    if not str(operation_id or "").strip():
        return ()
    store = OperationStore()
    try:
        operation = store.get_operation(operation_id)
        if operation is None or operation.status not in {"SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"}:
            return ()
        batches = store.coordination_batches_for_operation(operation_id)
        updated: list[CoordinationBatch] = []
        target = {
            "SUCCEEDED": "SUCCEEDED",
            "FAILED": "FAILED",
            "CANCELLED": "CANCELLED",
            "EXPIRED": "CANCELLED",
        }[operation.status]
        for batch in batches:
            if not _scope_matches(batch):
                continue
            step = next(
                (item for item in batch.steps if item.operation_id == operation_id and item.status == "WAITING_APPROVAL"),
                None,
            )
            if step is None:
                continue
            batch = store.transition_coordination_step(
                batch.batch_id,
                step.step_id,
                target,
                error_code="APPROVAL_EXPIRED" if operation.status == "EXPIRED" else None,
                error_message="确认已过期，未提交业务写入。" if operation.status == "EXPIRED" else None,
                event=_event(
                    batch,
                    "coordination.step.completed" if target == "SUCCEEDED" else "coordination.step.failed",
                    step,
                    status=target,
                ),
            )
            desired = batch_status_from_steps(batch.steps)
            if desired != batch.status:
                batch = store.transition_coordination_batch(
                    batch.batch_id,
                    desired,
                    expected_version=batch.version,
                    event=_event(batch, f"coordination.batch.{desired.lower()}", status=desired),
                )
            updated.append(batch)
        return tuple(updated)
    finally:
        store.close()


def public_summary(batch_id: str) -> dict[str, Any]:
    """返回给主 Agent 合成阶段的最小批次事实，不暴露 WorkOrder/内部令牌。"""

    store = OperationStore()
    try:
        batch = store.get_coordination_batch(batch_id, required=True)
    finally:
        store.close()
    assert batch is not None
    if not _scope_matches(batch):
        raise PermissionError("协作批次不属于当前用户或对话")
    return {
        "batchId": batch.batch_id,
        "status": batch.status,
        "steps": [
            {
                "stepId": step.step_id,
                "domain": step.domain,
                "actionId": step.action_id,
                "status": step.status,
                "errorCode": step.error_code,
                "errorMessage": step.error_message,
            }
            for step in batch.steps
        ],
    }


__all__ = [
    "COORDINATION_MARKER", "CoordinationTask", "load_tasks", "public_summary",
    "record_task_result", "start_tasks", "sync_operation_completion", "task_from_description",
]
