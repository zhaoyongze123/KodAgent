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
from typing import Annotated, Any, NotRequired

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langchain.agents.middleware.types import PrivateStateAttr

from ..orchestration.domain_dispatch import parse_work_order
from ..orchestration.execution_contracts import allowed_tools_for_executor


_PLAN_MARKER = "KODAGENT_CANONICAL_PLAN:"

_WORKFLOW_TOOLS = frozenset({
    "run_meeting_booking_workflow",
    "run_personal_schedule_workflow",
    "run_approval_write_workflow",
    "run_party_file_write_workflow",
})

# 项目一期只有只读执行器，但“只读”不表示模型可以在已编译委托中换一个项目。
# 这些映射把中央 canonicalPlan 的已验证请求范围重新填回工具参数；Java 仍会在
# 每次调用时复核项目成员关系、任务隐私和资料权限。
_PROJECT_READ_TOOL_FIELDS: dict[str, tuple[str, ...]] = {
    "list_accessible_projects": ("page_no", "page_size"),
    "analyze_project": ("project_id", "user_question"),
    "get_project_snapshot": ("project_id",),
    "get_project_tasks": ("project_id",),
    "get_project_activity": ("project_id", "from_time"),
    "get_project_documents": ("project_id",),
    "search_project_knowledge": ("project_id", "query", "top_k", "include_policy_library"),
}

# 进度播报不读取/修改业务事实，因此每份 WorkOrder 都可使用。其他工具必须由
# 中央 ExecutionContract 计算，不能靠子 Agent 的自然语言提示词放行。
_ALWAYS_ALLOWED_TOOLS = frozenset({"report_progress"})
_PROJECT_INVESTIGATION_TOOL_BUDGET = 6

# 编译器签发的“用户明确要求调查范围”到实际证据工具的一对一映射。基础
# analyze_project 不在这里，因为每个项目调查都会先执行它；这些映射只防止
# 资料、制度、任务明细或动态等已明确子目标被报告导出提前跳过。
_PROJECT_SCOPE_EVIDENCE_TOOLS: dict[str, str] = {
    "documents": "get_project_documents",
    "knowledge": "search_project_knowledge",
    "tasks": "get_project_tasks",
    "activity": "get_project_activity",
}

# 项目调查中的资料/制度检索不是开放式搜索面板。检索意图来自当前用户原话，
# 结果规模和制度库范围也应稳定，避免模型仅改 ``top_k`` 或布尔值就对同一批
# 项目资料重复发起一次实际相同的调用。若以后需要支持“再多找一些”这类明确
# 交互，应由编译器签发新的调查范围，而不是放开子 Agent 的自由参数。
_PROJECT_INVESTIGATION_KNOWLEDGE_DEFAULTS = {
    "top_k": 5,
    "include_policy_library": True,
}

_PROJECT_INVESTIGATION_EVIDENCE_KEY = "project_investigation_evidence"


def _merge_project_investigation_evidence(
    existing: dict[str, dict[str, Any]] | None,
    incoming: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """合并同一工具节点并发完成的项目调查证据。

    每项以 ``plan_id + tool + effective_fingerprint`` 为键，因此重复回放同一
    工具结果是幂等的；不同工具并行返回也不会覆盖彼此。这里保留的是运行内控制
    事实，不是项目业务事实，项目、任务和资料的权威来源仍是 Java Provider。
    """

    return {
        **(existing if isinstance(existing, dict) else {}),
        **(incoming if isinstance(incoming, dict) else {}),
    }


class ProjectInvestigationEvidenceState(AgentState):
    """项目子 Agent 本次委托实际完成工具的私有运行状态。

    ``messages`` 是给模型的对话记录，在 DeepAgents 的工具节点中可能只包含局部
    快照，不能作为重复调用与预算的唯一事实源。本字段由工具包装器在真实返回后
    写入 LangGraph 状态，再由下一次模型调用和下一次工具调用读取。

    ``PrivateStateAttr`` 保证它不会跨 ``task`` 回执泄漏给父 Agent，也不会被模型
    作为输入参数构造；它只服务于当前隔离子图的一次调查。
    """

    project_investigation_evidence: NotRequired[
        Annotated[
            dict[str, dict[str, Any]],
            PrivateStateAttr,
            # LangGraph 只将 ``Annotated`` 的最后一个 callable 识别为并发
            # reducer；私有标记可以处于前面，LangChain 仍会在输入/输出 schema
            # 构造时扫描到它。这个顺序使同一轮并发工具回执能合并而不互相覆盖。
            _merge_project_investigation_evidence,
        ]
    ]


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
    state_schema = ProjectInvestigationEvidenceState

    @classmethod
    def _allowed_tool_names(cls, work_order) -> frozenset[str]:
        """计算一次已编译委托在运行时真正允许调用的工具。

        WorkOrder 只携带 executor；helper 是 ExecutionContract 的稳定属性，
        因此旧 checkpoint 恢复时也会得到同样的授权结果。
        """
        allowed = _ALWAYS_ALLOWED_TOOLS | allowed_tools_for_executor(
            work_order.execution_tool
        )
        # 项目调查只负责取得 Java 复核后的事实。文件交付发生在主 Agent 提交最终
        # 正文之后，不能让子 Agent 预先调用固定模板导出器。
        return allowed

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

    @classmethod
    def _bound_project_read_args(
        cls,
        work_order,
        tool_name: str,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        """生成项目工具真正会收到的有效参数。

        这个函数同时服务于执行绑定和重复调用识别。此前两处各自读取一份参数：
        实际工具调用会被 ``_bind`` 改写为 canonicalPlan，而重复守卫却比较模型
        原始参数，导致模型换个检索措辞仍能重复查询同一份资料。现在比较和执行都
        以此处返回值为准，确保项目范围、检索问题和默认检索配置只有一个事实源。
        """

        canonical = dict(work_order.canonical_plan)
        bound = dict(args or {})
        bound.update({
            field: canonical[field]
            for field in _PROJECT_READ_TOOL_FIELDS.get(tool_name, ())
            if field in canonical
        })
        if tool_name == "analyze_project":
            # user_question 是调查上下文，不允许子 Agent 改写；project_id
            # 由同一份中央计划绑定。交付规格不是子 Agent 工具参数。
            bound["user_question"] = canonical.get("user_question", "")
        if (
            tool_name == "search_project_knowledge"
            and "knowledge" in set(canonical.get("requested_scopes") or ())
        ):
            # 检索词只能来自当前用户原话。模型可解释返回的证据，但不能将
            # “资料里有什么要注意”改造成另一项不相关的检索意图；同一调查中
            # 也不能靠变更分页或制度库开关重复读取相同证据。
            bound["query"] = canonical.get("user_question", "")
            bound.update(_PROJECT_INVESTIGATION_KNOWLEDGE_DEFAULTS)
        return bound

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
        if tool_name in _PROJECT_READ_TOOL_FIELDS:
            investigation = bool(
                work_order is not None
                and work_order.domain == "project"
                and work_order.action == "project.investigate"
            )
            if work_order is None or (work_order.execution_tool != tool_name and not investigation):
                return request
            bound_call = dict(call)
            bound_call["args"] = self._bound_project_read_args(
                work_order,
                tool_name,
                dict(call.get("args") or {}),
            )
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

    @staticmethod
    def _project_call_fingerprint(work_order, tool_name: str, args: dict[str, Any]) -> str:
        """按工具正式字段和已绑定项目范围生成稳定调用指纹。"""
        effective_args = WorkflowPlanBinderMiddleware._bound_project_read_args(
            work_order, tool_name, args,
        )
        normalized = {
            field: effective_args[field]
            for field in _PROJECT_READ_TOOL_FIELDS.get(tool_name, ())
            if field in effective_args
        }
        canonical = dict(work_order.canonical_plan)
        if "project_id" in _PROJECT_READ_TOOL_FIELDS.get(tool_name, ()):
            normalized["project_id"] = canonical.get("project_id")
        if tool_name == "analyze_project":
            normalized["user_question"] = canonical.get("user_question", "")
        try:
            return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError):
            return repr(normalized)

    @classmethod
    def _project_investigation_evidence(
        cls,
        state: dict[str, Any],
        work_order,
    ) -> dict[str, dict[str, Any]]:
        """读取当前 WorkOrder 已经实际完成的项目工具证据。

        只接受本次 ``plan_id`` 写入的结构化状态，避免另一次委托或模型自由文本
        被误当作本次调查结果。旧 checkpoint 没有该字段时返回空，由消息扫描兼容
        路径兜底；新的运行路径不会依赖那条兼容逻辑判重。
        """

        raw = (state or {}).get(_PROJECT_INVESTIGATION_EVIDENCE_KEY)
        if not isinstance(raw, dict):
            return {}
        plan_id = str(work_order.plan_id or "")
        evidence: dict[str, dict[str, Any]] = {}
        for key, item in raw.items():
            if not isinstance(key, str) or not isinstance(item, dict):
                continue
            if str(item.get("plan_id") or "") != plan_id:
                continue
            tool_name = str(item.get("tool") or "")
            fingerprint = str(item.get("fingerprint") or "")
            if tool_name not in _PROJECT_READ_TOOL_FIELDS or not fingerprint:
                continue
            evidence[key] = dict(item)
        return evidence

    @classmethod
    def _project_investigation_evidence_update(
        cls,
        request,
        response: ToolMessage,
    ) -> dict[str, dict[str, Any]] | None:
        """把一次真实工具返回转换为可供下一 ReAct 回合读取的状态更新。

        调用是否成功只在工具真正执行且返回 ``ToolMessage`` 后决定。这里不根据
        模型的 AI ToolCall 预写状态，避免“声明了但尚未执行”的调用错误占用预算。
        ``ok`` 同时保留 Java 的业务结果；业务失败会阻止无意义重试，但不会被当成
        可以支撑报告结论的成功事实。
        """

        call = getattr(request, "tool_call", None) or {}
        tool_name = str(call.get("name") or "")
        state = getattr(request, "state", {}) or {}
        work_order = cls._work_order(state)
        if not (
            work_order is not None
            and work_order.domain == "project"
            and work_order.action == "project.investigate"
            and tool_name in _PROJECT_READ_TOOL_FIELDS
        ):
            return None
        args = call.get("args") if isinstance(call.get("args"), dict) else {}
        fingerprint = cls._project_call_fingerprint(work_order, tool_name, args)
        successful = str(getattr(response, "status", "") or "").lower() != "error"
        try:
            payload = json.loads(str(response.content or ""))
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("ok"), bool):
            successful = bool(payload["ok"])
        evidence_key = "|".join((str(work_order.plan_id), tool_name, fingerprint))
        return {
            evidence_key: {
                "plan_id": str(work_order.plan_id),
                "tool": tool_name,
                "fingerprint": fingerprint,
                "ok": successful,
            }
        }

    @staticmethod
    def _command_with_project_evidence(
        response: ToolMessage | Command,
        evidence_update: dict[str, dict[str, Any]] | None,
    ) -> ToolMessage | Command:
        """把真实 ToolMessage 与私有证据状态作为同一原子更新提交。

        普通项目工具目前都会返回 ToolMessage。保留 ``Command`` 原样是为了不破坏
        未来含 HITL/跳转的工具契约；这类工具不写项目调查证据，必须在其自身的
        Command 中明确提供可验证的终止 ToolMessage 后再接入记录逻辑。
        """

        if not evidence_update or not isinstance(response, ToolMessage):
            return response
        return Command(
            update={
                "messages": [response],
                _PROJECT_INVESTIGATION_EVIDENCE_KEY: evidence_update,
            }
        )

    @classmethod
    def _project_investigation_history(cls, state: dict[str, Any], work_order) -> list[tuple[str, str]]:
        """读取当前子 Agent 回合已经完成的项目业务工具调用。

        LangGraph 在执行中间件前已经把“当前待执行”的 AI ToolCall 放进
        ``messages``。因此不能只扫描 AIMessage，否则第一次调用也会命中自己，
        被误判为重复。这里只接受已经出现同一 ``tool_call_id`` ToolMessage 的
        调用作为历史；自然语言、尚未执行的当前调用都不参与预算和重复判断。
        """
        state_evidence = cls._project_investigation_evidence(state, work_order)
        history = [
            (str(item["tool"]), str(item["fingerprint"]))
            for item in state_evidence.values()
        ]
        # 新运行通过私有状态通道得到完整的已执行事实，不再依赖 ToolMessage 的
        # 可见范围。保留下方历史扫描仅为旧 checkpoint、单元测试和灰度回放兼容。
        if state_evidence:
            return history

        completed_call_ids: set[str] = set()
        for message in (state or {}).get("messages") or []:
            if _message_type(message) != "tool":
                continue
            call_id = getattr(message, "tool_call_id", None)
            if isinstance(message, dict):
                call_id = call_id or message.get("tool_call_id")
            if call_id:
                completed_call_ids.add(str(call_id))

        history = []
        for message in (state or {}).get("messages") or []:
            if _message_type(message) != "ai":
                continue
            calls = getattr(message, "tool_calls", None)
            if isinstance(message, dict):
                calls = calls or message.get("tool_calls")
            for call in calls or []:
                if not isinstance(call, dict):
                    continue
                call_id = str(call.get("id") or "")
                if not call_id or call_id not in completed_call_ids:
                    continue
                name = str(call.get("name") or "")
                if name not in _PROJECT_READ_TOOL_FIELDS:
                    continue
                args = call.get("args") if isinstance(call.get("args"), dict) else {}
                fingerprint = cls._project_call_fingerprint(work_order, name, args)
                history.append((name, fingerprint))
        return history

    @staticmethod
    def _project_investigation_attempted_tools(state: dict[str, Any], work_order) -> set[str]:
        """读取本次调查中已经实际返回的项目证据工具。

        成功和业务失败都算“已尝试”：资料暂不可用时，报告应如实标注数据缺口，
        不能因导出被永久阻塞。尚未回写 ToolMessage 的模型声明不计入。
        """

        evidence = WorkflowPlanBinderMiddleware._project_investigation_evidence(
            state, work_order,
        )
        if evidence:
            return {str(item["tool"]) for item in evidence.values()}

        attempted: set[str] = set()
        for message in (state or {}).get("messages") or []:
            if _message_type(message) != "tool":
                continue
            name = getattr(message, "name", "")
            if isinstance(message, dict):
                name = message.get("name") or ""
            normalized = str(name or "")
            if normalized in _PROJECT_READ_TOOL_FIELDS:
                attempted.add(normalized)
        return attempted

    @classmethod
    def _missing_project_scope_evidence(cls, state: dict[str, Any], work_order) -> tuple[str, ...]:
        """返回导出前尚未实际查询的用户明确调查范围。"""

        scopes = work_order.canonical_plan.get("requested_scopes") or ()
        attempted = cls._project_investigation_attempted_tools(state, work_order)
        return tuple(
            scope
            for scope in scopes
            if _PROJECT_SCOPE_EVIDENCE_TOOLS.get(str(scope)) not in attempted
        )

    @classmethod
    def _project_investigation_completion_tools(
        cls,
        state: dict[str, Any],
        work_order,
    ) -> frozenset[str] | None:
        """计算项目调查事实已齐备后的唯一下一步工具集合。

        ``project.investigate`` 允许在取得基础分析后按用户明确范围补充资料、
        知识、任务或动态，这是领域内受控 ReAct；但当基础分析与这些范围都已有
        真实回执时，继续调用项目工具只会造成重试、重新检索或读取无关数据。

        返回值：
        * ``None``：调查仍缺少必要事实，保留常规项目工具面板；
        * 空集合：事实齐备，下一轮必须组织结论。

        这是一条运行控制规则，不替代 Java Project Provider 的项目、任务和权限
        事实来源，也不把候选或历史文本升级为业务事实。
        """

        if not (
            work_order.domain == "project"
            and work_order.action == "project.investigate"
        ):
            return None
        attempted = cls._project_investigation_attempted_tools(state, work_order)
        required_tools = {"analyze_project"}
        for scope in work_order.canonical_plan.get("requested_scopes") or ():
            tool_name = _PROJECT_SCOPE_EVIDENCE_TOOLS.get(str(scope))
            if tool_name:
                required_tools.add(tool_name)
        if not required_tools.issubset(attempted):
            return None
        return frozenset()

    def _project_investigation_blocked(self, request, work_order) -> ToolMessage | None:
        """执行项目自主调查的调用预算和重复调用守卫。"""
        if not (
            work_order.domain == "project"
            and work_order.action == "project.investigate"
        ):
            return None
        call = getattr(request, "tool_call", None) or {}
        tool_name = str(call.get("name") or "")
        if tool_name not in _PROJECT_READ_TOOL_FIELDS:
            return None
        if tool_name == "list_accessible_projects":
            return ToolMessage(
                content=json.dumps({"ok": False, "error": {
                    "code": "PROJECT_INVESTIGATION_SCOPE_REQUIRED",
                    "message": "项目调查已绑定唯一项目，不能重新枚举项目列表。",
                }}, ensure_ascii=False),
                tool_call_id=str(call.get("id") or "blocked-list-projects"),
                name=tool_name,
            )
        completion_tools = self._project_investigation_completion_tools(
            getattr(request, "state", {}) or {}, work_order,
        )
        if completion_tools is not None and tool_name not in completion_tools:
            return ToolMessage(
                content=json.dumps({"ok": False, "error": {
                    "code": "PROJECT_INVESTIGATION_COMPLETE",
                    "message": "项目调查所需事实已齐备，请基于现有结果生成结论；本次不再执行新的项目查询。",
                }}, ensure_ascii=False),
                tool_call_id=str(call.get("id") or f"blocked-complete-{tool_name}"),
                name=tool_name,
            )
        history = self._project_investigation_history(
            getattr(request, "state", {}) or {}, work_order,
        )
        args = call.get("args") if isinstance(call.get("args"), dict) else {}
        fingerprint = self._project_call_fingerprint(work_order, tool_name, args)
        if (tool_name, fingerprint) in history:
            code = "PROJECT_INVESTIGATION_DUPLICATE_CALL"
            message = "项目调查已执行过相同工具和参数，请基于已有事实继续分析或结束调查。"
        elif len(history) >= _PROJECT_INVESTIGATION_TOOL_BUDGET:
            code = "PROJECT_INVESTIGATION_BUDGET_EXCEEDED"
            message = f"项目调查最多允许 {_PROJECT_INVESTIGATION_TOOL_BUDGET} 次业务工具调用，请基于已有事实说明数据缺口。"
        else:
            return None
        return ToolMessage(
            content=json.dumps({"ok": False, "error": {"code": code, "message": message}}, ensure_ascii=False),
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
        investigation_blocked = self._project_investigation_blocked(request, work_order)
        if investigation_blocked is not None:
            return investigation_blocked
        if (
            tool_name in allowed
            and work_order.execution_tool in work_order.allowed_executors
        ):
            return None
        return self._blocked_tool_response(request, work_order.execution_tool)

    def wrap_tool_call(self, request, handler):
        blocked = self._guard(request)
        if blocked is not None:
            return blocked
        bound_request = self._bind(request)
        response = handler(bound_request)
        evidence_update = self._project_investigation_evidence_update(
            bound_request, response,
        ) if isinstance(response, ToolMessage) else None
        return self._command_with_project_evidence(response, evidence_update)

    async def awrap_tool_call(self, request, handler):
        blocked = self._guard(request)
        if blocked is not None:
            return blocked
        bound_request = self._bind(request)
        response = await handler(bound_request)
        evidence_update = self._project_investigation_evidence_update(
            bound_request, response,
        ) if isinstance(response, ToolMessage) else None
        return self._command_with_project_evidence(response, evidence_update)


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
        completion_tools = WorkflowPlanBinderMiddleware._project_investigation_completion_tools(
            getattr(request, "state", {}) or {}, work_order,
        )
        if completion_tools is not None:
            # 这里和 ``wrap_tool_call`` 使用同一完成状态：模型可见范围用于减少
            # 无效回合，执行守卫用于拦截兼容服务仍可能伪造的工具调用。
            allowed_names = completion_tools
        if (
            completion_tools is None
            and
            work_order.domain == "project"
            and work_order.action == "project.investigate"
            and "knowledge" in set(work_order.canonical_plan.get("requested_scopes") or ())
        ):
            history = WorkflowPlanBinderMiddleware._project_investigation_history(
                getattr(request, "state", {}) or {}, work_order,
            )
            if any(name == "search_project_knowledge" for name, _ in history):
                # 一次调查中的资料检索已被 canonicalPlan 固定为同一问题和同一
                # 检索配置。完成后直接从 palette 隐藏，避免模型再发起一轮并收到
                # 拒绝 ToolMessage；底层守卫继续覆盖旧 checkpoint 的直接调用。
                allowed_names = allowed_names - {"search_project_knowledge"}
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
    "ProjectInvestigationEvidenceState", "bind_workflow_call_args",
]
