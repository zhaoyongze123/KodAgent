"""把父 Agent 委托描述里的编译计划绑定到子 Agent 的工作流调用上。

架构拆分后，确定性写工作流（run_meeting_booking_workflow /
run_personal_schedule_workflow）的执行权从主 Agent 迁到了领域子 Agent：
主 Agent 只负责路由并把编译好的业务计划写进 ``task`` 描述
（见 plan_projection._delegate_description，带有 KODAGENT_WORK_ORDER
单行标记），子 Agent 负责查询、收集、字段校验，最后提交工作流。

子 Agent 没有主 Agent 的路由/投影中间件，因此本中间件在子 Agent 真正调用
工作流工具前，把描述里嵌入的权威计划重填进调用参数——防止子 Agent 改参数、
漏参数、把 UPDATE/CANCEL 误变成 CREATE，或丢失 source_booking_id /
source_schedule_id。这就是“工作流绑定关系从主 Agent 迁移到子 Agent”的落地：
谁执行工作流，谁就拥有参数绑定。
"""

from __future__ import annotations

import json
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

from ..orchestration.domain_dispatch import parse_work_order
from ..orchestration.execution_contracts import allowed_tools_for_executor


_PLAN_MARKER = "KODAGENT_CANONICAL_PLAN:"

_WORKFLOW_TOOLS = frozenset({
    "run_meeting_booking_workflow",
    "run_personal_schedule_workflow",
    "run_approval_write_workflow",
    "run_party_file_write_workflow",
})

# 进度播报不读取/修改业务事实，因此每份 WorkOrder 都可使用。其他工具必须由
# 中央 ExecutionContract 计算，不能靠子 Agent 的自然语言提示词放行。
_ALWAYS_ALLOWED_TOOLS = frozenset({"report_progress"})


def _message_text(message: Any) -> str:
    value = getattr(message, "content", "")
    if isinstance(message, dict):
        value = message.get("content", "")
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in value)
    return str(value or "")


def _message_type(message: Any) -> str:
    value = getattr(message, "type", None)
    if isinstance(message, dict):
        value = message.get("type") or message.get("role")
    return str(value or "").lower()


def _tool_name(tool: Any) -> str:
    """兼容 LangChain Tool 对象和 OpenAI 风格字典，读取工具名称。"""
    if isinstance(tool, dict):
        function = tool.get("function")
        return str(tool.get("name") or (function or {}).get("name") or "")
    return str(getattr(tool, "name", "") or "")


def bind_workflow_call_args(tool_name: str, canonical: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """把权威 ``canonical`` 计划重新绑定到工作流工具调用参数。

    参数：
        tool_name：本次受控工作流的正式工具名称。
        canonical：中央编译得到的权威计划，是操作类型、目标对象和业务字段的
            唯一事实源。
        args：模型或子 Agent 原本提供的参数；会被复制后按计划重填。

    返回：
        可安全交给工作流的参数。与主 Agent 侧
        ``plan_projection._bind_compiled_call`` 保持同一字段映射：
        ``operation``/``source_*`` 等“谁操作、操作哪条”的字段由编译计划拥有，
        时间、参会人、标题等业务字段也以计划为准，防止重试时被篡改或丢失。
    """
    bound = dict(args)
    if tool_name == "run_meeting_booking_workflow":
        operation = canonical.get("operation")
        if operation:
            bound["operation"] = operation
        if canonical.get("sourceBookingId") is not None:
            bound["source_booking_id"] = canonical["sourceBookingId"]
        field_map = {
            "subject": "subject", "start_time": "start_time", "end_time": "end_time",
            "attendees": "attendee_names", "room_capacity": "room_capacity",
            "equipment": "equipment", "room_preference": "room_preference",
            "remark": "remark", "reason": "cancel_reason",
        }
        for source, target in field_map.items():
            if source in canonical:
                bound[target] = canonical[source]
        return bound
    if tool_name == "run_personal_schedule_workflow":
        operation = canonical.get("operation")
        if operation:
            bound["operation"] = operation
        if canonical.get("sourceScheduleId") is not None:
            bound["source_schedule_id"] = canonical["sourceScheduleId"]
        field_map = {
            "title": "title", "start_time": "start_time", "end_time": "end_time",
            "description": "description", "location": "location",
            "attendees": "attendee_user_ids", "other_participants": "other_participants",
        }
        for source, target in field_map.items():
            if source in canonical:
                bound[target] = canonical[source]
        return bound
    if tool_name == "run_approval_write_workflow":
        # 编译器使用 CREATE 表示发起申请，审批适配器使用 REQUEST 区分它与
        # 待办动作；映射只在这个契约边界发生一次。
        operation = str(canonical.get("operation") or "").upper()
        bound["operation"] = {"CREATE": "REQUEST"}.get(operation, operation)
        field_map = {
            "process_definition": "process_definition",
            "processDefinition": "process_definition",
            "variables": "variables",
            "startUserSelectAssignees": "start_user_select_assignees",
            "processInstanceId": "process_instance_id",
            "taskId": "task_id",
            "taskIds": "task_ids",
            "action": "action",
            "reason": "reason",
            "criteria": "criteria",
        }
        for source, target in field_map.items():
            if source in canonical:
                bound[target] = canonical[source]
        return bound
    if tool_name == "run_party_file_write_workflow":
        operation = canonical.get("operation")
        if operation:
            bound["operation"] = operation
        if canonical.get("sourcePartyFileId") is not None:
            bound["source_party_file_id"] = canonical["sourcePartyFileId"]
        field_map = {
            "title": "title", "content": "content", "category_id": "category_id",
            "category_name": "category_name", "summary": "summary",
            "publish_time": "publish_time", "targets": "targets",
            "distribute_to_self": "distribute_to_self", "storage_type": "storage_type",
            "status": "status", "document_type": "document_type",
        }
        for source, target in field_map.items():
            if source in canonical:
                bound[target] = canonical[source]
        if "attachment_file_ids" in canonical:
            attachment_ids = canonical["attachment_file_ids"]
            bound["attachment_file_ids"] = (
                ",".join(str(item) for item in attachment_ids)
                if isinstance(attachment_ids, list) else attachment_ids
            )
        return bound
    return bound


class WorkflowPlanBinderMiddleware(AgentMiddleware):
    """绑定并守卫领域子 Agent 的工作流调用。

    文件职责：把主 Agent 的 WorkOrder（控制面）转换为子 Agent 可以执行的
    确定性工作流参数（数据面）。带 WorkOrder 的写操作只能走其中指定的
    ``executionTool``，不能先调用若干低层工具再自行拼出一个草稿。
    """

    name = "WorkflowPlanBinderMiddleware"

    @classmethod
    def _allowed_tool_names(cls, work_order) -> frozenset[str]:
        """计算一次已编译委托在运行时真正允许调用的工具。

        WorkOrder 只携带 executor；helper 是 ExecutionContract 的稳定属性，
        因此旧 checkpoint 恢复时也会得到同样的授权结果。
        """
        return _ALWAYS_ALLOWED_TOOLS | allowed_tools_for_executor(
            work_order.execution_tool
        )

    @staticmethod
    def _canonical_plan(state: dict[str, Any]) -> dict[str, Any] | None:
        """Parse a WorkOrder, then fall back to legacy canonical-plan turns.

        # 子 Agent 的任务描述是父级写入的唯一 HumanMessage；标记后的 JSON 是
        # 紧凑单行（json.dumps 默认无换行），按行截断即可安全解析。没有标记
        # 说明本次调用不是“已编译计划的委托”，不绑定。
        """
        for message in reversed((state or {}).get("messages") or []):
            if _message_type(message) not in {"human", "user"}:
                continue
            content = _message_text(message)
            work_order = parse_work_order(content)
            if work_order is not None:
                return dict(work_order.canonical_plan)
            marker_index = content.find(_PLAN_MARKER)
            if marker_index < 0:
                continue
            plan_json = content[marker_index + len(_PLAN_MARKER):].splitlines()[0].strip()
            if not plan_json:
                continue
            try:
                payload = json.loads(plan_json)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                return payload
        return None

    @staticmethod
    def _work_order(state: dict[str, Any]):
        for message in reversed((state or {}).get("messages") or []):
            if _message_type(message) in {"human", "user"}:
                work_order = parse_work_order(_message_text(message))
                if work_order is not None:
                    return work_order
        return None

    def _bind(self, request) -> Any:
        call = getattr(request, "tool_call", None)
        if not isinstance(call, dict):
            return request
        tool_name = str(call.get("name") or "")
        state = getattr(request, "state", {}) or {}
        work_order = self._work_order(state)
        # 目标核验 WorkOrder 的 executor 是只读详情工具，不属于写工作流。ID 仍
        # 必须由中央编译计划绑定，防止子 Agent 用候选摘要或模型猜测改查另一条。
        if tool_name in {"get_personal_schedule", "get_my_meeting_booking"}:
            if work_order is None or not bool(work_order.canonical_plan.get("targetResolution")):
                return request
            if work_order.execution_tool != tool_name:
                return request
            source_key = "sourceScheduleId" if tool_name == "get_personal_schedule" else "sourceBookingId"
            source_id = work_order.canonical_plan.get(source_key)
            if source_id is None:
                return request
            bound_call = dict(call)
            bound_call["args"] = {
                **dict(call.get("args") or {}),
                "schedule_id" if tool_name == "get_personal_schedule" else "booking_id": source_id,
            }
            return request.override(tool_call=bound_call)
        if tool_name not in _WORKFLOW_TOOLS:
            return request
        if work_order is not None and (
            work_order.execution_tool != tool_name
            or tool_name not in work_order.allowed_executors
        ):
            # A child may use helper read tools, but it cannot turn a compiled
            # WorkOrder into another workflow/write executor.
            return request
        canonical = self._canonical_plan(state)
        if not canonical:
            return request
        args = dict(call.get("args") or {})
        bound = bind_workflow_call_args(tool_name, canonical, args)
        bound_call = dict(call)
        bound_call["args"] = bound
        return request.override(tool_call=bound_call)

    def _blocked_tool_response(self, request, expected_tool: str) -> ToolMessage:
        """返回结构化拒绝结果，不执行越过 WorkOrder 授权范围的工具。"""
        call = getattr(request, "tool_call", None) or {}
        tool_name = str(call.get("name") or "unknown_tool")
        return ToolMessage(
            content=json.dumps({
                "ok": False,
                "error": {
                    "code": "WORK_ORDER_TOOL_NOT_ALLOWED",
                    "message": f"当前委托只允许核验后执行 {expected_tool}，不能调用 {tool_name}。",
                },
            }, ensure_ascii=False),
            tool_call_id=str(call.get("id") or f"blocked-{tool_name}"),
            name=tool_name,
        )

    def _guard(self, request) -> ToolMessage | None:
        """对所有已编译委托强制执行“执行器 + helper”授权边界。

        过去只保护 workflow 写操作，读委托会重新打开整个领域 palette；现在
        不论读写，只要携带 WorkOrder 就使用同一份中央契约计算 allow-list。
        """
        call = getattr(request, "tool_call", None)
        if not isinstance(call, dict):
            return None
        work_order = self._work_order(getattr(request, "state", {}) or {})
        if work_order is None:
            return None
        tool_name = str(call.get("name") or "")
        allowed = self._allowed_tool_names(work_order)
        if (
            tool_name in allowed
            and work_order.execution_tool in work_order.allowed_executors
        ):
            return None
        return self._blocked_tool_response(request, work_order.execution_tool)

    def wrap_tool_call(self, request, handler):
        blocked = self._guard(request)
        return blocked if blocked is not None else handler(self._bind(request))

    async def awrap_tool_call(self, request, handler):
        blocked = self._guard(request)
        return blocked if blocked is not None else await handler(self._bind(request))


class WorkOrderToolProjectionMiddleware(AgentMiddleware):
    """在模型调用前按 WorkOrder 隐藏无关领域工具。

    文件职责：完整 palette 仍由 registry 保存，保证领域能力不丢；这个类只在
    一次已经编译的委托中创建“有效工具视图”，减少模型上下文噪声。真正的
    安全仍由 ``WorkflowPlanBinderMiddleware.wrap_tool_call`` 守卫保证；本类
    不继承该守卫，避免同一次工具调用被两个 middleware 重复处理。
    """

    name = "WorkOrderToolProjectionMiddleware"

    def _project(self, request):
        work_order = WorkflowPlanBinderMiddleware._work_order(
            getattr(request, "state", {}) or {}
        )
        if work_order is None:
            return request
        allowed_names = WorkflowPlanBinderMiddleware._allowed_tool_names(work_order)
        return request.override(
            tools=[
                tool for tool in (getattr(request, "tools", ()) or ())
                if _tool_name(tool) in allowed_names
            ]
        )

    def wrap_model_call(self, request, handler):
        return handler(self._project(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._project(request))


__all__ = [
    "WorkflowPlanBinderMiddleware", "WorkOrderToolProjectionMiddleware",
    "bind_workflow_call_args",
]
