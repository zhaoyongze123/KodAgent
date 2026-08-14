"""不直接访问业务系统的会话控制工具。

文件职责
========
本模块定义 ``route_conversation`` 等控制面工具：它们把用户文本、当前上下文和
Action Catalog 编译成可验证的路由结果或澄清结果，但不直接预约会议、写审批或
修改日程。业务系统调用必须在后续执行器中发生。

结构导读
========
* 输入模型：校验两阶段路由所需的能力域、动作和候选计划；
* 规范化函数：统一日期、查询条件和领域字段；
* ``route_conversation``：编译计划并返回结构化路由事实；
* 结果转换函数：将内部异常和状态转换为工具契约规定的响应。
"""

import ast
from copy import deepcopy
import json
import re
from typing import Any, Literal

from langchain.tools import tool
from pydantic import BaseModel, Field, field_validator

from ...domain.conversation import ExecutionClass, RouteStrategy
from ...orchestration.routing.router import classify_message, set_route_reasoning_policy
from ...orchestration.routing.recovery import (
    party_file_attachment_plan,
    party_metadata_fallback_plan,
    recover_party_file_write_candidate,
    recover_party_file_write_intent,
    normalize_schedule_query_candidate,
    schedule_metadata_fallback_plan,
    meeting_metadata_fallback_plan,
    normalize_meeting_query_candidate,
    recover_meeting_write_action,
)
from ...orchestration.capabilities import (
    APPROVAL_PROCESS_CAPABILITY_ID,
    CAPABILITIES,
    GENERAL_CAPABILITY,
    action_catalog_prompt,
    action_description,
    action_execution_class,
    action_field_specs,
    action_required_fields,
    action_read_only,
    action_requires_confirmation,
    actions_for_capability,
    canonical_capability_id,
    capability_routing_enabled,
    is_non_action_reference,
    resolve_action,
    resolve_registered_action_alias,
    resolve_capability,
    resolve_typed_read_action,
    suggest_action_id_from_payload,
)
from ...orchestration.action_catalog_runtime import runtime_action_catalog_meta
from ...orchestration.prompts import PROMPT_VERSION
from ...orchestration.routing_trace import current_model_trace
from ...orchestration.skill_registry import skill_registry
from ...orchestration.query_canonicalizer import canonicalize_approval_query
from ...orchestration.action_selection import (
    recover_approval_process_action,
    recover_approval_read_action,
)
from ...orchestration.compiler import compile_plan
from ...orchestration.coordination_compiler import (
    CoordinationCandidateStep,
    CoordinationCompilationError,
    compile_coordination_batch,
)
from ...orchestration.conversation_context import ContextIntent, verify_context_candidate_proof
from ...orchestration.target_resolution import target_resolution_compiled_route
from ...orchestration.planning.party_file import normalize_party_file_operation
from ...orchestration.planning.resources import infer_workflow_capability
from ...persistence.operation_store import OperationStore
from .events import current_agent_context, emit
from langgraph.config import get_stream_writer
from .contracts import ToolResponse, tool_failure, tool_success

class RouteConversationInput(BaseModel):
    """两阶段路由工具的类型化输入边界。

    ``capability_id`` 在两个阶段都必填：第一阶段从已注册领域中选择一个，确实
    无法识别时才使用 ``general_agent``；第二阶段保持同一领域并补充 ``action_id``
    和候选业务字段。强制传入领域可防止模型悄悄遗漏“确定性业务计划”和通用
    ReAct 回退之间最关键的事实。

    字段说明：
        message：当前用户原始请求；只能用于理解意图，不能代替授权业务事实。
        capability_id：第一阶段选定的能力域，后续阶段不得随意更换。
        action_id：第二阶段从实时 Action Catalog 中逐字选择的正式动作标识。
        candidate_plan：用户明确提供或工具真实返回的候选业务字段，编译器会继续
            校验其完整性、权限和来源对象。
        context_candidate_id：主图 checkpoint 签发的上下文候选引用。模型只能选择
            已展示的候选；候选只会触发 Java 定向核验，不能在本参数或业务计划中
            伪造来源字段。
        context_intent：模型对本轮与上下文关系的结构化判断。它只影响路由和澄清，
            不能授予业务对象写权限或替代正式审批卡。
        context_confidence：模型对 context_intent 的置信度。引用已授权对象这种会
            影响写计划的意图，低置信度只能进入澄清，不能绑定来源字段。
    """

    message: str
    continuation_mode: Literal["resume", "new"] | None = Field(
        default=None,
        description=(
            "仅表示当前输入是否续接 Thread 中待补字段的计划；这是传输提示，"
            "不参与业务计划编译。"
        ),
    )
    task_complexity: Literal["simple", "complex"] = "simple"
    capability_id: str = Field(
        ...,
        description="第一阶段选择的能力域；未知请求必须传 general_agent，不能省略。",
    )
    action_id: str | None = Field(
        default=None,
        description=(
            "第二阶段才填写；必须从当前路由工具 schema 的 action_id 枚举中逐字复制。"
            "不能填写工具名、子 Agent 名称、自然语言或历史别名。"
        ),
    )
    strategy: RouteStrategy | None = None
    confidence: float | None = None
    missing_fields: list[str] | None = None
    unsupported_criteria: list[str] | None = None
    query_intent: dict | str | None = None
    execution_class: ExecutionClass | None = None
    context_candidate_id: str | None = Field(
        default=None,
        min_length=16,
        max_length=128,
        description=(
            "仅传当前提示词展示的上下文候选 ID；界面返回的 sourceResultId/result:... 不是候选 ID，"
            "也不能用它代替 source_*_id 或审批确认。"
        ),
    )
    context_intent: ContextIntent = Field(
        default="NEW_REQUEST",
        description=(
            "本轮上下文意图：NEW_REQUEST=新请求；RESUME_PENDING_PLAN=补充待补计划；"
            "REFER_TO_QUERY_CANDIDATE=修改/取消已授权业务对象；"
            "LOCATE_APPROVAL_CARD=定位待确认操作；AMBIGUOUS=多个候选无法唯一确定。"
        ),
    )
    context_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="对 context_intent 的置信度，取值 0 到 1；不确定时传较低值并选择 AMBIGUOUS。",
    )
    candidate_plan: dict[str, Any] | str | None = Field(
        default=None,
        description=(
            "只填写用户明确提供或真实工具返回的业务字段。更新/取消必须使用"
            "本轮 Java 已授权业务事实中的 source_*_id；不能猜测或从历史上下文选目标。"
            "键名必须使用 Action Catalog 的正式字段名，值类型与格式遵循其"
            "字段格式约定：datetime 为 yyyy-MM-dd HH:mm:ss，date 为 yyyy-MM-dd，"
            "integer 为纯数字，array 为字符串数组；缺失字段不要编造。"
        ),
    )
    steps: list[CoordinationCandidateStep] | None = Field(
        default=None,
        min_length=2,
        max_length=4,
        description=(
            "仅用于一次请求包含 2 到 4 个相互独立领域动作的跨领域路由。每项必须"
            "填写稳定 step_id、正式 capability_id、action_id、execution_class 与结构化 candidate_plan。"
            "步骤会分别经过中央编译并生成 WorkOrder；不得填写工具名、子 Agent 名称、"
            "依赖关系或上一步结果中的业务 ID。"
        ),
    )

    @field_validator("missing_fields", "unsupported_criteria", mode="before")
    @classmethod
    def _coerce_string_lists(cls, value: Any) -> Any:
        """兼容供应商把数组编码为 JSON 字符串的情况，同时保持字段 Schema。"""
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return [text]
        return parsed if isinstance(parsed, list) else [str(parsed)]


class _ModelToolSchema(dict[str, Any]):
    """兼容 OpenAI 的工具描述，同时提供稳定的 ``name`` 访问方式。

    LangChain 模型消费字典形式；中间件诊断和边界校验则需要读取工具名称。两种
    视图共用同一对象，可避免各个工具投影边界重复实现不一致的名称解析器。
    """

    @property
    def name(self) -> str:
        function = self.get("function")
        return str(function.get("name") or "") if isinstance(function, dict) else ""


def route_conversation_model_schema(
    capability_id: str | None = None,
    *,
    selected_action_id: str | None = None,
    require_action: bool = False,
) -> dict[str, Any]:
    """根据实时 Action Catalog 构造本回合面向模型的路由工具 Schema。

    可执行的 ``route_conversation`` 工具保持稳定的传输 Schema，供 LangGraph 在
    模型调用后按名称解析。模型调用前，投影中间件会调用本工厂生成本回合专用的
    JSON Schema，因此模型只能选择当前已注册的能力域；进入领域后，也只能选择
    该领域当前有效的 ``action_id``。Java 同步的动作目录会经由
    ``actions_for_capability`` 自动反映到这里，提示词中不复制任何动作名称。

    参数：
        capability_id：已锁定的能力域；为空时提供完整能力域枚举。
        selected_action_id：已知的正式动作标识，用于进一步收紧枚举。
        require_action：是否要求本次调用必须提交 ``action_id``。
    """
    parameters = deepcopy(RouteConversationInput.model_json_schema())
    properties = parameters.setdefault("properties", {})
    required = list(parameters.get("required") or [])

    selected_capability = canonical_capability_id(capability_id)
    capability_values = (
        [selected_capability]
        if selected_capability and selected_capability not in {"general", "general_agent"}
        else [item.name for item in (*CAPABILITIES, GENERAL_CAPABILITY)]
    )
    properties["capability_id"] = {
        "type": "string",
        "enum": capability_values,
        "description": "从当前路由工具 schema 的 capability_id 枚举中选择。",
    }

    action_values = [item.action_id for item in actions_for_capability(selected_capability)]
    if selected_action_id:
        # A field-clarification/resume turn has an already compiled action.
        # Its schema is narrower than the domain catalog so the model cannot
        # turn an UPDATE into CREATE while filling a missing field.
        action_values = [selected_action_id] if selected_action_id in action_values else []
    if action_values:
        properties["action_id"] = {
            "type": "string",
            "enum": action_values,
            "description": "从当前 action_id 枚举中逐字选择正式动作。",
        }
        if require_action and "action_id" not in required:
            required.append("action_id")
    elif not require_action:
        # 第一阶段不向模型暴露 action_id：该阶段字段没有枚举约束，弱模型会
        # 提前编造未注册动作名导致整轮路由失败。能力域锁定后（action_values
        # 非空）才在第二阶段暴露带枚举的正式动作列表。需要强制动作的
        # HANDSHAKE 回合保留字段，避免模型无动作可提交。
        properties.pop("action_id", None)
        if "action_id" in required:
            required.remove("action_id")
    parameters["required"] = required

    return _ModelToolSchema({
        "type": "function",
        "function": {
            "name": route_conversation.name,
            "description": route_conversation.description,
            "parameters": parameters,
        },
    })


def _meeting_write_contains_explicit_field_signal(message: str) -> bool:
    """判断预约原文是否已含值得由第二阶段模型落位的字段线索。

    这里只判断“是否需要保留用户已给信息”，不提取字段值、更不从文本生成业务
    计划。实际标题、时间、人员等仍必须由模型按 Action Catalog 的 schema 写入
    ``candidate_plan``，随后交给 PlanCompiler 校验。没有任何字段线索时保留原有
    的直接字段澄清，避免为了一个空计划额外发起模型交握。
    """

    text = str(message or "")
    return bool(re.search(
        r"主题|题目|会议名称|议题|参会人|参加人|\d{1,2}\s*(?:点|时|:)|"
        r"(?:今天|明天|后天|周[一二三四五六日天]|下周|上午|下午|晚上)",
        text,
    ))


def _coerce_object(value: Any) -> dict[str, Any] | None:
    """Normalize provider tool arguments without moving routing into prose.

    A few OpenAI-compatible tool-call adapters serialize an object argument as
    a JSON string.  The route contract is still the same typed object; this
    adapter only repairs the transport representation and rejects arbitrary
    text.  ``ast.literal_eval`` is limited to literals and supports providers
    that emit Python-style single-quoted dictionaries.
    """
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
        except (TypeError, ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            return dict(parsed)
    return None


_ACTION_FIELD_ALIASES: dict[str, dict[str, str]] = {
    # These are transport spellings emitted by model/tool adapters. They are
    # normalized to the catalog field only; authorization markers are never
    # synthesized here.
    "meeting.update": {
        "booking_id": "source_booking_id", "bookingId": "source_booking_id",
        "reservation_id": "source_booking_id", "reservationId": "source_booking_id",
    },
    "meeting.cancel": {
        "booking_id": "source_booking_id", "bookingId": "source_booking_id",
        "reservation_id": "source_booking_id", "reservationId": "source_booking_id",
    },
    "schedule.update": {
        "schedule_id": "source_schedule_id", "scheduleId": "source_schedule_id",
        "event_id": "source_schedule_id", "eventId": "source_schedule_id",
    },
    "schedule.cancel": {
        "schedule_id": "source_schedule_id", "scheduleId": "source_schedule_id",
        "event_id": "source_schedule_id", "eventId": "source_schedule_id",
    },
    "approval.process.application_detail": {
        "process_id": "processInstanceId", "process_instance_id": "processInstanceId",
        "processInstanceID": "processInstanceId",
    },
    "approval.process.withdraw": {
        "process_id": "processInstanceId", "process_instance_id": "processInstanceId",
        "processInstanceID": "processInstanceId",
    },
    "party_file.attachments": {
        "file_id": "source_party_file_id", "fileId": "source_party_file_id",
        "document_id": "source_party_file_id", "documentId": "source_party_file_id",
    },
    "party_file.update": {
        "file_id": "source_party_file_id", "fileId": "source_party_file_id",
        "document_id": "source_party_file_id", "documentId": "source_party_file_id",
    },
    "party_file.delete": {
        "file_id": "source_party_file_id", "fileId": "source_party_file_id",
        "document_id": "source_party_file_id", "documentId": "source_party_file_id",
    },
    "party_file.compare": {
        "left_id": "left_file_id", "leftFileId": "left_file_id",
        "right_id": "right_file_id", "rightFileId": "right_file_id",
    },
}

_EXPLICIT_REFERENCE_PATTERNS: dict[str, re.Pattern[str]] = {
    "meeting_source": re.compile(r"(?:预约(?:编号|号)?|booking(?:\s*id)?|会议)\s*(?:为|是)?\s*[#：:#-]?\s*(\d+)", re.I),
    "schedule_source": re.compile(r"(?:日程(?:编号|号)?|schedule(?:\s*id)?|event(?:\s*id)?)\s*(?:为|是)?\s*[#：:#-]?\s*(\d+)", re.I),
    "party_file_source": re.compile(r"(?:党务文件|文件|文档)(?:编号|号)?\s*(?:为|是)?\s*[#：:#-]?\s*(\d+)", re.I),
    "process_instance": re.compile(r"流程(?:编号|号)?\s*(?:为|是)?\s*[#：:#-]?\s*([A-Za-z0-9_-]+)", re.I),
    "approval_task": re.compile(r"任务(?:编号|号)?\s*(?:为|是)?\s*[#：:#-]?\s*([A-Za-z0-9_-]+)", re.I),
}


def _normalize_action_field_aliases(
    action_id: str | None,
    candidate_plan: dict[str, Any] | None,
    query_intent: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Normalize typed transport keys without creating business authority."""
    aliases = _ACTION_FIELD_ALIASES.get(str(action_id or "").strip(), {})
    candidate = dict(candidate_plan or {})
    intent = dict(query_intent or {})
    for payload in (intent, candidate):
        for source, target in aliases.items():
            if target not in payload and source in payload:
                payload[target] = payload[source]
            if source != target:
                payload.pop(source, None)
    return candidate, intent if query_intent is not None else None


def _recover_explicit_reference_fields(
    action_id: str | None,
    message: str,
    candidate_plan: dict[str, Any],
) -> dict[str, Any]:
    """Extract explicitly labelled IDs without treating them as authorized."""
    action = str(action_id or "").strip()
    payload = dict(candidate_plan)
    if action in {"meeting.update", "meeting.cancel"} and "source_booking_id" not in payload:
        match = _EXPLICIT_REFERENCE_PATTERNS["meeting_source"].search(message)
        if match:
            payload["source_booking_id"] = int(match.group(1))
    elif action in {"schedule.update", "schedule.cancel"} and "source_schedule_id" not in payload:
        match = _EXPLICIT_REFERENCE_PATTERNS["schedule_source"].search(message)
        if match:
            payload["source_schedule_id"] = int(match.group(1))
    elif action in {"party_file.attachments", "party_file.update", "party_file.delete"} and "source_party_file_id" not in payload:
        match = _EXPLICIT_REFERENCE_PATTERNS["party_file_source"].search(message)
        if match:
            payload["source_party_file_id"] = int(match.group(1))
    elif action in {"approval.process.application_detail", "approval.process.withdraw"} and "processInstanceId" not in payload:
        match = _EXPLICIT_REFERENCE_PATTERNS["process_instance"].search(message)
        if match:
            payload["processInstanceId"] = match.group(1)
    elif action == "approval.write.task" and "taskId" not in payload:
        match = _EXPLICIT_REFERENCE_PATTERNS["approval_task"].search(message)
        if match:
            payload["taskId"] = match.group(1)
    elif action == "approval.write.batch" and "taskIds" not in payload:
        values = _EXPLICIT_REFERENCE_PATTERNS["approval_task"].findall(message)
        if values:
            payload["taskIds"] = values
    elif action == "party_file.compare":
        values = _EXPLICIT_REFERENCE_PATTERNS["party_file_source"].findall(message)
        if len(values) >= 2:
            payload.setdefault("left_file_id", int(values[0]))
            payload.setdefault("right_file_id", int(values[1]))
    elif action == "party_file.compliance":
        file_match = _EXPLICIT_REFERENCE_PATTERNS["party_file_source"].search(message)
        task_match = _EXPLICIT_REFERENCE_PATTERNS["approval_task"].search(message)
        if file_match:
            payload.setdefault("file_id", int(file_match.group(1)))
        if task_match:
            payload.setdefault("task_id", task_match.group(1))
    return payload


# Backwards-compatible alias. The canonical implementation lives in the
# orchestration capability registry so the projection middleware and the
# route policy share exactly one copy of the inference contract.
_suggest_action_id_from_payload = suggest_action_id_from_payload


def _infer_typed_action_from_shape(
    capability_id: str | None,
    execution_class: str | None,
    candidate_plan: dict[str, Any] | None,
    query_intent: dict[str, Any] | None,
    message: str = "",
) -> tuple[str, str, str] | None:
    """Recover a domain/action only from an explicit typed payload shape.

    This is intentionally narrower than the removed operation-only fallback:
    a bare ``QUERY`` or ``CREATE`` remains unsupported.  The payload must
    contain an entity or fields that uniquely identify one registered action.
    """
    candidate = candidate_plan if isinstance(candidate_plan, dict) else {}
    intent = query_intent if isinstance(query_intent, dict) else {}
    entity = str(
        candidate.get("entity") or candidate.get("type") or candidate.get("object_type")
        or candidate.get("objectType") or intent.get("entity") or intent.get("type") or ""
    ).strip().lower().replace("-", "_")
    operation = str(
        candidate.get("operation") or candidate.get("action")
        or intent.get("operation") or intent.get("action") or ""
    ).strip().upper().replace("-", "_")
    canonical_capability = canonical_capability_id(capability_id)
    if canonical_capability and canonical_capability not in {"", "general", "general_agent"}:
        # Capability aliases belong to the transport boundary. Typed action
        # recovery must operate on the canonical catalog namespace or a
        # delegate name such as ``meeting_rooms_agent`` will block a valid
        # operation from resolving to ``meeting.create``.
        domain = canonical_capability
    elif entity in {"my_requests", "my_applications", "approval_applications"} and re.search(
        r"我发起|我的申请|发起的审批|申请记录", str(message or "")
    ):
        return "approval_process", "approval.process.applications", "approval_query"
    elif entity in {
        "pending_approval", "approval", "approval_task", "approvals", "todo",
        "pending", "pending_approvals", "my_pending", "my_requests", "my_approvals",
    }:
        # ``my_requests`` is a provider alias that is ambiguous in isolation.
        # In the absence of explicit “我发起/我的申请” wording, the OA
        # product's short “找审批” query means the user's pending inbox.
        domain = "approval_read"
        entity = "pending_approval"
    elif entity in {"meeting", "meeting_booking", "meeting_room", "room_booking"}:
        domain = "meeting"
    elif entity in {"schedule", "personal_schedule", "calendar"}:
        domain = "schedule"
    elif entity in {"party_file", "party_files", "partyfile", "party_document"}:
        domain = "party_file"
    else:
        sort_values = candidate.get("sort") or intent.get("sort") or []
        # A few providers encode a typed approval ranking as
        # ``order_by="create_time desc"`` instead of the registered ``sort``
        # array.  Treat only known approval sort fields as the compatibility
        # signal; an arbitrary ``limit`` or generic CRUD verb remains
        # ambiguous and still falls back to the normal domain planner.
        raw_order = candidate.get("order_by") or candidate.get("orderBy") or intent.get("order_by") or intent.get("orderBy")
        if raw_order and not sort_values:
            sort_values = [raw_order] if isinstance(raw_order, str) else raw_order
        if isinstance(sort_values, str):
            sort_values = [sort_values]
        sort_fields = {
            str(
                item.get("field") if isinstance(item, dict) else str(item).split()[0]
            ).lower().replace("createtime", "created_time")
            for item in sort_values
        }
        if (
            sort_fields & {"amount", "created_time", "create_time", "process_type", "pending_days", "processdefinitionname"}
            or (
                sort_fields & {"recent", "latest", "newest"}
                and re.search(r"审批|待办|流程", str(message or ""))
            )
        ):
            domain = "approval_read"
        elif sort_fields & {"publishtime", "publish_time", "title", "categoryname"}:
            domain = "party_file"
        elif any(key in candidate or key in intent for key in ("start_time", "end_time", "source_booking_id")):
            domain = "meeting" if "booking" in entity or "meeting" in entity else "schedule"
        else:
            return None
    if domain == "approval_read":
        has_approval_shape = (
            entity in {"pending_approval", "approval", "approval_task", "approvals"}
            or operation in {"QUERY", "LIST", "SEARCH", "RANK", "FILTER", "ANALYZE"}
            or bool(candidate.get("sort") or candidate.get("filters") or candidate.get("limit") is not None
                    or intent.get("sort") or intent.get("filters") or intent.get("limit") is not None)
        )
        if not has_approval_shape:
            return None
        return domain, "approval.read.pending", "metadata_query"
    if domain == "meeting" and operation in {"BOOK", "CREATE", "CREATE_DRAFT", "UPDATE", "CANCEL", "DELETE"}:
        action = {"BOOK": "meeting.create", "CREATE": "meeting.create", "CREATE_DRAFT": "meeting.create",
                  "UPDATE": "meeting.update", "CANCEL": "meeting.cancel", "DELETE": "meeting.cancel"}[operation]
        return domain, action, "workflow"
    if domain == "schedule":
        if operation in {"QUERY", "LIST", "SEARCH", "CALENDAR"}:
            return domain, "schedule.query", "metadata_query"
        if operation in {"CREATE", "CREATE_DRAFT", "NEW"}:
            return domain, "schedule.create", "workflow"
        if operation in {"UPDATE", "EDIT"}:
            return domain, "schedule.update", "workflow"
        if operation in {"CANCEL", "DELETE"}:
            return domain, "schedule.cancel", "workflow"
    if domain == "party_file":
        if operation in {"ATTACHMENTS", "ATTACHMENT", "ATTACHMENT_QUERY"}:
            return domain, "party_file.attachments", "metadata_query"
        if operation in {"CREATE", "PUBLISH", "DRAFT", "DRAFT_AND_PUBLISH"}:
            return domain, "party_file.create", "workflow"
        if operation in {"UPDATE", "EDIT"}:
            return domain, "party_file.update", "workflow"
        if operation in {"DELETE", "REMOVE", "VOID"}:
            return domain, "party_file.delete", "workflow"
        if operation in {"QUERY", "LIST", "SEARCH", "METADATA_QUERY"}:
            return domain, "party_file.metadata", "metadata_query"
    return None


def _recover_typed_workflow_candidate(
    message: str,
    candidate_plan: dict[str, Any] | None,
    query_intent: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Normalize a provider's partially emitted typed workflow envelope.

    Some OpenAI-compatible providers emit ``query_intent`` but omit the
    top-level ``capability_id`` and ``candidate_plan`` fields.  The query
    intent is still a structured object, so losing those fields should not
    send an otherwise unambiguous request into the ReAct fallback.  This
    helper only accepts explicit domain/shape markers; it never classifies
    free-form prose.
    """
    candidate = dict(candidate_plan) if isinstance(candidate_plan, dict) else {}
    intent = dict(query_intent) if isinstance(query_intent, dict) else {}

    # Some providers emit a typed personal-schedule payload but omit the
    # entity/domain field. Recover that omission only when the user message
    # explicitly names a personal schedule and the payload contains the
    # structured fields that prove it. A generic CREATE remains ambiguous.
    text = str(message or "")
    explicit_personal_schedule = bool(re.search(r"个人日程|个人安排|我的日程", text))
    merged = {**intent, **candidate}
    nested_fields = candidate.get("draft_fields") or candidate.get("draftFields")
    if isinstance(nested_fields, dict):
        merged = {**nested_fields, **merged}

    # Some providers put the complete party-file intent in query_intent but
    # omit candidate_plan. This is typed schema recovery, not prose routing.
    # Keep confirmation distinct from CREATE: only an official ApprovalCard
    # resume may call confirm_* and a plain “确认发布” must not mint a draft.
    party_action = str(intent.get("action") or intent.get("operation") or "").strip().upper().replace("-", "_")
    party_domain = str(
        intent.get("entity") or intent.get("domain") or intent.get("type") or intent.get("document_type") or ""
    ).strip().lower().replace("-", "_")
    party_shape = any(
        intent.get(key) not in (None, "", [], {})
        for key in ("title", "document_type", "date_range", "audience", "activities", "requirement", "background", "confirmation")
    )
    party_action_is_typed = any(marker in party_action for marker in (
        "PARTY_FILE", "PARTY_DOCUMENT", "DRAFT_AND_PUBLISH", "PUBLISH_PARTY", "CREATE_PARTY",
    ))
    # Providers may emit a generic CRUD operation together with a typed
    # ``document_type``/``title`` intent, while omitting both the party-file
    # entity and the longer ``draft_and_publish_party_document`` action.  That
    # envelope is still unambiguous: a document type plus a title is not a
    # meeting or personal-schedule plan.  Recover the registered party-file
    # workflow instead of delegating to the read-only child agent.
    typed_party_document = bool(
        str(intent.get("document_type") or intent.get("documentType") or "").strip()
        and str(intent.get("title") or "").strip()
    )
    if party_action_is_typed or party_domain in {"party_file", "party_files", "party_document", "party_notice"} or typed_party_document:
        confirmation_action = "CONFIRM" in party_action or bool(intent.get("confirmation"))
        if confirmation_action:
            return {**candidate, **intent, "entity": "party_file", "operation": "CONFIRM", "_confirmation_intent": True}
        party_operation = normalize_party_file_operation(
            intent.get("operation") or intent.get("action")
        )
        party_operation = {
            "DRAFT_AND_PUBLISH_PARTY_DOCUMENT": "CREATE",
            "PUBLISH_PARTY_FILE": "CREATE",
        }.get(party_operation, party_operation)
        if party_operation in {"CREATE", "UPDATE", "DELETE"} or party_shape:
            return {**candidate, **intent, "entity": "party_file", "operation": party_operation or "CREATE"}
    operation = str(merged.get("operation") or merged.get("action") or "").strip().upper()
    operation = {
        "NEW": "CREATE", "CREATE_DRAFT": "CREATE", "CREATE_SCHEDULE": "CREATE",
        "CREATE_PERSONAL_SCHEDULE": "CREATE", "UPDATE_SCHEDULE": "UPDATE",
        "EDIT": "UPDATE", "CHANGE": "UPDATE", "RESCHEDULE": "UPDATE",
        "CANCEL": "CANCEL", "DELETE": "CANCEL", "DELETE_SCHEDULE": "CANCEL",
    }.get(operation, operation)
    has_schedule_fields = (
        bool(str(merged.get("title") or merged.get("summary") or "").strip())
        and any(merged.get(key) not in (None, "") for key in ("start_time", "startTime", "start"))
        and any(merged.get(key) not in (None, "") for key in ("end_time", "endTime", "end"))
    )
    typed_schedule = explicit_personal_schedule and operation in {"CREATE", "UPDATE", "CANCEL"} and (
        has_schedule_fields or any(
            key in merged for key in ("source_schedule_id", "sourceScheduleId", "schedule_id", "scheduleId")
        )
    )
    if typed_schedule:
        normalized = {**candidate, **intent, "type": "personal_schedule", "operation": operation}
        if isinstance(nested_fields, dict):
            normalized = {**nested_fields, **normalized}
        normalized["entity"] = "personal_schedule"
        return normalized

    if candidate:
        return candidate
    if not intent:
        return None

    raw_domain = intent.get("entity") or intent.get("domain") or intent.get("type")
    domain = str(raw_domain or "").strip().lower().replace("-", "_")
    meeting_markers = {
        "meeting", "meeting_room", "meeting_booking", "meetingroom",
        "room_booking", "conference_room", "会议", "会议室",
    }
    schedule_markers = {
        "schedule", "personal_schedule", "calendar", "日程", "个人日程",
    }

    # ``attendees`` plus a bounded start/end interval is the typed shape used
    # by the meeting-booking planner.  It is intentionally not a prose or
    # keyword route; callers that do not provide this shape remain fallback.
    is_meeting = domain in meeting_markers or (
        "attendees" in intent
        and any(key in intent for key in ("start_time", "start"))
        and any(key in intent for key in ("end_time", "end"))
    )
    is_schedule = domain in schedule_markers
    if not is_meeting and not is_schedule:
        return None

    operation = str(
        intent.get("operation")
        or intent.get("action")
        or ""
    ).strip().upper()
    operation = {
        "CREATE": "BOOK" if is_meeting else "CREATE",
        "NEW": "BOOK" if is_meeting else "CREATE",
        "BOOK": "BOOK",
        "UPDATE": "UPDATE",
        "EDIT": "UPDATE",
        "CHANGE": "UPDATE",
        "RESCHEDULE": "UPDATE",
        "CANCEL": "CANCEL",
        "DELETE": "CANCEL",
        "REMOVE": "CANCEL",
    }.get(operation, operation)
    if operation not in {"BOOK", "UPDATE", "CANCEL", "CREATE"}:
        return None
    if is_meeting and operation == "CREATE":
        operation = "BOOK"
    # Preserve the structured business fields when only the outer route
    # envelope was dropped.  Returning only operation/type silently discarded
    # start/end/title and made strict action validation ask for fields the
    # provider had already extracted.
    return {
        **intent,
        "operation": operation,
        "type": "meeting_booking" if is_meeting else "personal_schedule",
    }


def _context_clarification_response(
    *,
    intent: ContextIntent,
    question: str,
    issue: str,
    candidate_id: str | None = None,
) -> ToolResponse:
    """返回上下文层的确定性澄清结果，绝不把短句直接编译为写操作。"""

    data = {
        "routeState": "CONFIRMATION_REQUIRED" if intent == "LOCATE_APPROVAL_CARD" else "FIELD_CLARIFICATION",
        "planStatus": "CLARIFY",
        "contextIntent": intent,
        "clarification": {
            "status": "CLARIFY",
            "question": question,
            "issues": [issue],
            "missingFields": [],
            **({"contextCandidateId": candidate_id} if candidate_id else {}),
        },
    }
    return tool_success(
        data,
        {
            "blockType": "card",
            "cardType": "clarification",
            "resultKind": "clarification",
            "summary": {"headline": question},
            "actions": [],
        },
    )


def _recover_typed_schedule_query_candidate(
    message: str,
    candidate_plan: dict[str, Any] | None,
    query_intent: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Recover a schedule metadata query when the provider drops its envelope.

    The recovery is limited to a typed personal-schedule query shape. It does
    not inspect arbitrary prose for a route; the explicit operation plus a
    date/range field must already be present in the candidate/query object.
    """
    candidate = dict(candidate_plan) if isinstance(candidate_plan, dict) else {}
    intent = dict(query_intent) if isinstance(query_intent, dict) else {}
    merged = {**intent, **candidate}
    operation = str(merged.get("operation") or merged.get("action") or "").strip().upper()
    operation = {"LIST": "QUERY", "SEARCH": "QUERY", "CALENDAR": "QUERY"}.get(operation, operation)
    schedule_type = str(
        merged.get("schedule_type") or merged.get("scheduleType")
        or merged.get("entity") or merged.get("type") or ""
    ).strip().lower().replace("-", "_")
    date = str(merged.get("date") or "").strip()
    start = str(merged.get("start_time") or merged.get("startTime") or "").strip()
    end = str(merged.get("end_time") or merged.get("endTime") or "").strip()
    time_range = merged.get("time_range") or merged.get("timeRange")
    # ``schedule_type=personal`` is already a typed domain assertion from the
    # planner. The message check is only a secondary guard for providers that
    # omit that field; do not require the model to repeat the word ``个人`` in
    # a shortened route message.
    explicit_schedule = schedule_type in {"personal", "personal_schedule", "schedule", "calendar"} or bool(
        re.search(r"个人日程|个人安排|我的日程|个人日历|我的日历", str(message or ""))
    )
    if operation != "QUERY" or not explicit_schedule:
        return None
    if schedule_type and schedule_type not in {"personal", "personal_schedule", "schedule", "calendar"}:
        return None
    if not date and not (start and end) and not isinstance(time_range, dict):
        return None
    normalized = {**candidate, **intent, "entity": "personal_schedule", "operation": "QUERY"}
    # Providers often repeat a one-day date as both ``date`` and a full-day
    # interval. The action contract accepts either representation, so retain
    # the more precise interval when both describe the same calendar day.
    if date and start and end and start[:10] == date and end[:10] == date:
        normalized.pop("date", None)
    return normalized


def _coordination_step_summaries(steps: tuple[Any, ...]) -> list[dict[str, Any]]:
    """将已签发批次投影为可给主 Agent 看的最小步骤摘要。

    ``CoordinationBatch`` 内的 ``work_order`` 是子 Agent 的执行契约，可能包含
    业务字段和内部来源信息。主 Agent 后续只需拿 ``batchId`` 交给协调执行桥，
    不应从模型上下文重新拼装 WorkOrder，因此这里绝不回传完整 WorkOrder。
    """

    return [
        {
            "stepId": str(step.step_id),
            "domain": str(step.domain),
            "actionId": str(step.action_id),
            "executorTool": str(step.executor_tool),
            # 让后续协调执行桥能审计每步是否仍使用编译器签发的唯一 executor，
            # 但不返回 canonicalPlan 或任何 source_*_id，避免主模型重组业务事实。
            "workOrderSafety": {
                "schemaVersion": (step.work_order or {}).get("schemaVersion"),
                "planId": (step.work_order or {}).get("planId"),
                "allowedCapabilities": (step.work_order or {}).get("allowedCapabilities", []),
                "allowedActions": (step.work_order or {}).get("allowedActions", []),
                "allowedExecutors": (step.work_order or {}).get("allowedExecutors", []),
            },
        }
        for step in steps
    ]


def _compile_coordination_route(
    *,
    message: str,
    steps: list[CoordinationCandidateStep] | list[dict[str, Any]],
) -> ToolResponse:
    """编译并持久化一次跨领域批次，但不在路由层执行任何子 Agent。

    参数：
        message：当前用户原文，只作为 WorkOrder 的澄清上下文和审计摘要。
        steps：模型提交的 2 到 4 项独立候选步骤；每项都必须走现有
            ``compile_plan -> WorkOrder`` 链路。

    返回：成功时只返回批次 ID 和步骤摘要。协调器随后从 PostgreSQL 读取同一批次
    并执行；失败时返回结构化澄清，保证任何未完整编译的步骤都不会被派发。
    """

    # ``route_conversation.func`` 在单元测试和少量内部调用中会绕过 LangChain 的
    # Pydantic 输入适配，因此在入口再做一次严格转换，线上和测试使用同一契约。
    try:
        proposals = [
            item if isinstance(item, CoordinationCandidateStep)
            else CoordinationCandidateStep.model_validate(item)
            for item in steps
        ]
    except (TypeError, ValueError) as exc:
        return tool_success({
            "routeState": "FIELD_CLARIFICATION",
            "planStatus": "CLARIFY",
            "clarification": {
                "status": "CLARIFY",
                "question": "跨领域请求的每个步骤都需要提供领域、动作类型和结构化条件。",
                "issues": [f"跨领域步骤格式无效：{exc}"],
                "missingFields": ["steps"],
            },
        })

    runtime = current_agent_context()
    required_context = {
        "tenant_id": str(runtime.get("tenantId") or "").strip(),
        "user_id": str(runtime.get("userId") or "").strip(),
        "thread_id": str(runtime.get("threadId") or "").strip(),
        "run_id": str(runtime.get("runId") or "").strip(),
        "message_id": str(runtime.get("messageId") or "").strip(),
    }
    missing_context = [name for name, value in required_context.items() if not value]
    if missing_context:
        # 批次必须绑定真实的用户、Thread、Run 和消息。不能为了让本轮通过而用
        # local-* 伪值落库，否则恢复、审计和后续 HITL 无法确认它属于谁。
        return tool_failure(
            "COORDINATION_CONTEXT_INVALID",
            "当前跨领域请求缺少运行上下文，无法安全创建协作批次。",
            details={"missing": missing_context},
            retryable=False,
            user_action="请重新发起当前请求。",
        )

    try:
        batch = compile_coordination_batch(
            proposals,
            tenant_id=required_context["tenant_id"],
            user_id=required_context["user_id"],
            thread_id=required_context["thread_id"],
            run_id=required_context["run_id"],
            origin_run_id=str(runtime.get("originRunId") or required_context["run_id"]).strip(),
            message_id=required_context["message_id"],
            user_context=message,
        )
    except CoordinationCompilationError as exc:
        # 中央编译是原子边界：任一步不符合 Action Catalog、WorkOrder 或特性开关，
        # 整批都不会得到 batch ID，更不会出现“部分步骤绕过计划直接执行”。
        return tool_success({
            "routeState": "FIELD_CLARIFICATION",
            "planStatus": "CLARIFY",
            "clarification": {
                "status": "CLARIFY",
                "question": "这组跨领域请求中有步骤尚不能执行，请补充或拆分后重试。",
                "issues": [str(exc)],
                "missingFields": [],
            },
        })

    try:
        store = OperationStore()
        try:
            persisted = store.create_coordination_batch(batch)
        finally:
            store.close()
    except Exception:
        # 不把数据库连接、SQL 或认证细节传给模型。未持久化就不能交给后续协调器，
        # 因此这里必须失败而不是返回一个只存在于内存中的 batch ID。
        return tool_failure(
            "COORDINATION_PERSISTENCE_UNAVAILABLE",
            "跨领域协作状态暂时无法保存，请稍后重试。",
            retryable=True,
        )

    result = {
        # 这是给后续主图协调桥识别的明确事实，不伪装成单领域 RESOLVED 计划；
        # 它没有单一 executor，不能被现有单 WorkOrder 派发逻辑误处理。
        "routeState": "COORDINATION_READY",
        "planStatus": "COORDINATION_READY",
        "coordinationBatch": {
            "batchId": persisted.batch_id,
            "status": persisted.status,
            "stepCount": len(persisted.steps),
            "steps": _coordination_step_summaries(persisted.steps),
        },
        "routeDecision": {
            "capabilityId": "coordination",
            "strategy": "coordinate",
            "confidence": 1.0,
        },
    }
    try:
        writer = get_stream_writer()
    except RuntimeError:
        writer = None
    if writer is not None:
        emit(
            writer,
            "coordination.batch.created",
            f"已编译 {len(persisted.steps)} 个独立领域步骤，等待协调执行。",
            batchId=persisted.batch_id,
            stepCount=len(persisted.steps),
            status=persisted.status,
        )
    return tool_success(result)


@tool(args_schema=RouteConversationInput)
def route_conversation(
    message: str,
    continuation_mode: Literal["resume", "new"] | None = None,
    task_complexity: Literal["simple", "complex"] = "simple",
    capability_id: str | None = None,
    action_id: str | None = None,
    strategy: RouteStrategy | None = None,
    confidence: float | None = None,
    missing_fields: list[str] | None = None,
    unsupported_criteria: list[str] | None = None,
    query_intent: dict | str | None = None,
    execution_class: ExecutionClass | None = None,
    context_candidate_id: str | None = None,
    context_intent: ContextIntent = "NEW_REQUEST",
    context_confidence: float | None = None,
    candidate_plan: dict[str, Any] | str | None = None,
    steps: list[CoordinationCandidateStep] | None = None,
) -> ToolResponse:
    """校验主 Agent 提出的能力选择和任务复杂度，不执行业务操作。

    capability_id 必须来自当前能力目录；不确定时传 general_agent，不能
    编造未注册的业务能力。已选择领域后，action_id 必须来自该领域的动作目录；
    模型不能传工具名或 Java 路径。若 ``steps`` 非空，必须是 2 到 4 个互不依赖
    的跨领域候选步骤；它们仍由中央编译为独立 WorkOrder，路由工具不执行它们。
    Runtime 会校验 direct/delegate/clarify 边界。
    """
    if steps is not None:
        return _compile_coordination_route(message=message, steps=steps)

    # Keep the public schema tolerant of the provider's object-as-string
    # encoding, then immediately restore the canonical in-memory shape.  No
    # business routing is inferred from the user's prose here.
    candidate_plan = _coerce_object(candidate_plan)
    # 服务端后续可能为了兼容旧供应商补入 ``action_id``、``operation`` 或做
    # 窄范围动作纠偏；这些字段不能倒过来证明“模型已经提交了完整计划”。保留
    # 这一时刻的原始事实，才能在会议写操作的首轮正确进入二阶段动作选择。
    model_supplied_candidate_plan = isinstance(candidate_plan, dict) and bool(candidate_plan)
    context_intent = str(context_intent or "NEW_REQUEST").strip().upper()  # type: ignore[assignment]
    if context_intent not in {
        "NEW_REQUEST", "RESUME_PENDING_PLAN", "REFER_TO_QUERY_CANDIDATE",
        "LOCATE_APPROVAL_CARD", "AMBIGUOUS",
    }:
        context_intent = "AMBIGUOUS"  # type: ignore[assignment]
    # 当模型选择上下文候选时，内部证明只能由 PlanToolProjectionMiddleware 在
    # 清洗模型参数后、从可信 checkpoint 注入。普通模型调用无法伪造 HMAC，因此
    # 不能靠填写授权标记取得来源 ID。未携带候选 ID 的历史内部调用仍由其原有
    # 上游边界负责来源标记；主图投影层会先剥离模型直接提交的同名字段。
    trusted_context_candidate = bool(
        isinstance(candidate_plan, dict)
        and verify_context_candidate_proof(
            context_candidate_id, candidate_plan.get("_context_candidate_proof"),
        )
    )
    if isinstance(candidate_plan, dict):
        candidate_plan = dict(candidate_plan)
        candidate_plan.pop("_context_candidate_proof", None)
        if context_candidate_id and not trusted_context_candidate:
            candidate_plan.pop("_authorized_source_fields", None)
    candidate_kind = str((candidate_plan or {}).get("_context_candidate_kind") or "")
    target_resolution = (
        dict((candidate_plan or {}).get("_target_resolution") or {})
        if isinstance((candidate_plan or {}).get("_target_resolution"), dict)
        else None
    )
    if isinstance(candidate_plan, dict):
        # 内部核验标记不属于 Action Catalog 的业务字段。它只在本工具返回路由
        # 之前被读取，普通编译器永远看不到候选 source ID。
        candidate_plan.pop("_target_resolution", None)
    if context_intent == "AMBIGUOUS":
        return _context_clarification_response(
            intent="AMBIGUOUS",
            question="当前有多个可能相关的事项，请说明名称或第几个事项。",
            issue="上下文候选不唯一，不能自动选择业务对象。",
        )
    if context_intent == "LOCATE_APPROVAL_CARD":
        if trusted_context_candidate and candidate_kind == "pending_approval":
            return _context_clarification_response(
                intent="LOCATE_APPROVAL_CARD",
                question="已定位到待确认操作。请使用当前有效的确认卡完成确认或取消。",
                issue="普通文本不能替代 ApprovalCard；系统会以 Java 当前 PENDING 状态为准。",
                candidate_id=context_candidate_id,
            )
        return _context_clarification_response(
            intent="LOCATE_APPROVAL_CARD",
            question="没有找到当前有效的待确认操作，请重新生成草稿或从待办中选择。",
            issue="待确认操作可能已处理、过期或不属于当前 Thread。",
        )
    if context_intent == "REFER_TO_QUERY_CANDIDATE" and (
        context_confidence is not None and context_confidence < 0.70
    ):
        return _context_clarification_response(
            intent="AMBIGUOUS",
            question="我还不能确定你指的是哪一项，请说名称或第几个事项。",
            issue="上下文意图置信度不足，不能为修改或取消操作自动绑定对象。",
        )
    explicit_candidate_supplied = model_supplied_candidate_plan
    query_intent = _coerce_object(query_intent)
    # Textual schedule-date recovery is a provider-envelope compatibility
    # path. Once the provider supplied any structured plan/intent, time
    # semantics belong to that contract and must be compiled or clarified.
    provider_schedule_envelope_missing = not explicit_candidate_supplied and not bool(query_intent)
    initial_confirmation_intent = bool(
        isinstance(candidate_plan, dict)
        and (
            candidate_plan.get("_confirmation_intent") is True
            or str(candidate_plan.get("operation") or candidate_plan.get("action") or "")
            .strip()
            .upper()
            in {"CONFIRM", "CONFIRM_PUBLISH", "CONFIRM_RELEASE"}
        )
    )
    action_recovery: dict[str, str] | None = None
    schedule_date_recovery: dict[str, str] | None = None
    action_id = str(
        action_id
        or (candidate_plan or {}).get("action_id")
        or (candidate_plan or {}).get("actionId")
        or (query_intent or {}).get("action_id")
        or (query_intent or {}).get("actionId")
        or ""
    ).strip() or None
    requested_action_id = action_id
    # Conversation history is carried by the LangGraph checkpoint. It is not
    # a mutable business fact source, so route recovery never selects a write
    # target from a thread-wide Redis task projection. UPDATE/CANCEL plans must
    # carry an explicit, compiler-authorized source ID.
    route = classify_message(message, task_complexity=task_complexity)
    party_file_attachment = party_file_attachment_plan(message, candidate_plan, capability_id)
    # Structured source IDs are accepted only from the candidate plan and are
    # revalidated by the domain compiler/Java facade. A free-form follow-up
    # without an explicit source must remain a clarification.
    # Attachment inspection/delivery has precedence over party-file CRUD. A
    # provider-produced CREATE candidate cannot override this read-only
    # boundary when the user did not ask to create or publish a document.
    if party_file_attachment and party_file_attachment.get("status") == "RESOLVED":
        capability_id = "party_file"
        action_id = "party_file.attachments"
        execution_class = "metadata_query"
        candidate_plan = {
            "operation": "ATTACHMENTS",
            "source_party_file_id": party_file_attachment["source_party_file_id"],
            "action": "inspect",
            "_authorized_source_fields": party_file_attachment.get("_authorized_source_fields", []),
        }
        strategy = "direct"
        confidence = 1.0
        explicit_candidate_supplied = True
    elif party_file_attachment and party_file_attachment.get("status") == "CLARIFY":
        capability_id = "party_file"
        execution_class = "metadata_query"
        strategy = "clarify"
        confidence = 1.0
        candidate_plan = {"operation": "ATTACHMENTS"}
        # Do not retain a provider's CREATE payload while asking for the
        # source file. Otherwise a clarification turn could mint a draft.
        explicit_candidate_supplied = False

    # Normalize registered provider aliases before typed recovery runs. This
    # keeps the compatibility boundary in the Action Catalog instead of
    # scattering legacy names through prompts or executors.
    action_hint = resolve_action(capability_id, action_id) if action_id else None
    if action_hint is not None:
        if action_id != action_hint.action_id:
            action_recovery = {
                "from": str(action_id),
                "to": action_hint.action_id,
                "reason": "registered_action_alias",
            }
        candidate_plan = {
            **(candidate_plan or {}),
            "action_id": action_hint.action_id,
            "operation": action_hint.operation,
        }
        explicit_candidate_supplied = True
    # OpenAI-compatible providers occasionally omit one of the routing
    # envelope fields while still returning a typed, registered operation
    # (for example ``candidate_plan={operation: BOOK}``).  Recover only this
    # schema-level fact; never infer from free-form user prose.  A known
    # operation is sufficient to recover both the workflow class and domain,
    # otherwise the request remains on the general fallback path.
    recovered_candidate = _recover_typed_workflow_candidate(message, candidate_plan, query_intent)
    if recovered_candidate is not None:
        candidate_plan = recovered_candidate
    recovered_schedule_query = _recover_typed_schedule_query_candidate(message, candidate_plan, query_intent)
    if recovered_schedule_query is not None:
        candidate_plan = recovered_schedule_query
        if not capability_id or str(capability_id).strip() in {"general_agent", "general"}:
            capability_id = "schedule"
        if execution_class in {None, "metadata_query"}:
            execution_class = "metadata_query"
    recovered_party_file = recover_party_file_write_candidate(message, candidate_plan)
    if recovered_party_file is not None:
        candidate_plan = recovered_party_file
        # A typed party-file write is a hard execution-boundary assertion.
        # Never preserve a provider's broad content/document class here: that
        # would compile to FALLBACK and expose the read-only child agent.
        execution_class = "workflow"
        capability_id = "party_file"
    # A provider can drop the complete typed candidate, not just one envelope
    # field.  Do one bounded recovery for an unmistakable party-file write so
    # a supported request cannot fall through to general-agent prose.  This
    # helper intentionally returns only the operation/entity; business fields
    # and all authorization facts still come from the normal draft tool and
    # Java facade.
    if recovered_party_file is None:
        recovered_party_file_intent = recover_party_file_write_intent(message, candidate_plan)
        if recovered_party_file_intent is not None:
            candidate_plan = recovered_party_file_intent
            execution_class = "workflow"
            capability_id = "party_file"

    # If the provider supplied an unregistered action id, recover only a
    # uniquely identifiable read action from the selected domain's declared
    # fields. Writes deliberately never use this path: they must name a
    # registered action so an invalid model action cannot select a workflow.
    if (
        not initial_confirmation_intent
        and action_id
        and resolve_action(capability_id, action_id) is None
        and not is_non_action_reference(action_id)
    ):
        recovered_process = recover_approval_process_action(message)
        if (
            recovered_process is not None
            and str(capability_id or "").strip().lower()
            in {"approval_read", "approval", "approvals", APPROVAL_PROCESS_CAPABILITY_ID}
            and resolve_registered_action_alias(action_id) is None
        ):
            capability_id = "approval_process"
            action_id = recovered_process["action_id"]
            execution_class = recovered_process.get("execution_class") or execution_class
            candidate_plan = dict(recovered_process.get("candidate_plan") or {})
            explicit_candidate_supplied = True
            action_recovery = {
                "from": str(requested_action_id or ""),
                "to": action_id,
                "reason": "explicit_approval_scope_boundary",
            }
        registered_alias = resolve_registered_action_alias(action_id)
        if action_id and registered_alias is not None:
            previous_action_id = action_id
            action_id = registered_alias.action_id
            capability_id = registered_alias.capability_id
            execution_class = registered_alias.execution_class
            candidate_plan = {
                **(query_intent or {}),
                **(candidate_plan or {}),
                "action_id": registered_alias.action_id,
                "operation": registered_alias.operation,
            }
            action_recovery = {
                "from": str(previous_action_id),
                "to": registered_alias.action_id,
                "reason": "registered_action_alias",
            }
            explicit_candidate_supplied = True
        typed_read_action = resolve_typed_read_action(
            capability_id,
            execution_class,
            candidate_plan=candidate_plan,
            query_intent=query_intent,
        )
        if typed_read_action is not None:
            action_recovery = {
                "from": str(action_id),
                "to": typed_read_action.action_id,
                "reason": "unique_read_schema_match",
            }
            capability_id = typed_read_action.capability_id
            action_id = typed_read_action.action_id
            execution_class = typed_read_action.execution_class
            candidate_plan = {
                **(query_intent or {}),
                **(candidate_plan or {}),
                "action_id": typed_read_action.action_id,
                "operation": typed_read_action.operation,
            }
            explicit_candidate_supplied = True
            if typed_read_action.action_id == "schedule.query":
                normalized_schedule = _recover_typed_schedule_query_candidate(
                    message, candidate_plan, query_intent
                )
                if normalized_schedule is not None:
                    candidate_plan = normalized_schedule

    # A confirmation is a resume signal for a persisted ApprovalCard, not a
    # new business action.  Keep it out of the ordinary action-selection
    # handshake: that handshake is for choosing CREATE/UPDATE/DELETE, while a
    # plain confirmation must never mint a new draft or expose a write tool.
    # The marker is produced only by the typed party-file confirmation shape;
    # the message-only branch below is limited to an already selected
    # party-file capability so a generic "确认" cannot be misrouted.
    confirmation_intent = bool(
        isinstance(candidate_plan, dict)
        and (
            candidate_plan.get("_confirmation_intent") is True
            or str(candidate_plan.get("operation") or candidate_plan.get("action") or "")
            .strip()
            .upper()
            in {"CONFIRM", "CONFIRM_PUBLISH", "CONFIRM_RELEASE"}
        )
    )
    if not confirmation_intent and context_intent == "LOCATE_APPROVAL_CARD" and str(capability_id or "").strip().lower() in {
        "party_file", "party_files", "party_files_agent"
    }:
        confirmation_intent = True
        capability_id = "party_file"
        execution_class = "workflow"
        candidate_plan = {
            "entity": "party_file",
            "operation": "CONFIRM",
            "_confirmation_intent": True,
        }
    if confirmation_intent:
        # A stale provider action id (for example party_file.create) must not
        # survive a confirmation-only turn. The durable ApprovalCard owns the
        # operation; this route call only explains how to resume it.
        action_id = None
        candidate_plan = {
            "entity": "party_file",
            "operation": "CONFIRM",
            "_confirmation_intent": True,
        }

    # A model/provider may put a delegate name or a guessed query label in
    # ``action_id`` even when the user request is an unmistakable read-only
    # personal-calendar query. Repair that namespace drift only at this
    # bounded read boundary. Never use message prose to recover a write
    # action, a source id, or another domain's executor.
    schedule_fallback = schedule_metadata_fallback_plan(message) if provider_schedule_envelope_missing else None
    canonical_capability = canonical_capability_id(capability_id)
    selected_action = resolve_action(capability_id, action_id) if action_id else None
    if (
        schedule_fallback is not None
        and not confirmation_intent
        and canonical_capability == "schedule"
        # A provider may label a read-only calendar request as content_search,
        # workflow or another transport class. The explicit user intent and
        # the selected read action are the stronger contract; an explicit
        # write action is excluded by the selected_action guard above.
        and (selected_action is None or selected_action.action_id == "schedule.query")
    ):
        previous_action_id = action_id
        capability_id = schedule_fallback["capability_id"]
        execution_class = schedule_fallback["execution_class"]
        candidate_plan = {
            **(candidate_plan or {}),
            **schedule_fallback["candidate_plan"],
        }
        action_id = "schedule.query"
        explicit_candidate_supplied = True
        if previous_action_id != action_id:
            action_recovery = {
                "from": str(previous_action_id or ""),
                "to": action_id,
                "reason": "bounded_personal_calendar_read",
            }

    # A provider can select the approval-read domain while dropping the
    # second-stage action and typed query envelope. Repeating the same route
    # call cannot add information and was observed to create a loop. Recover
    # only the domain-scoped, structurally unambiguous list/analysis action;
    # all other approval requests still receive ACTION_SELECTION.
    if (
        not confirmation_intent
        and not action_id
        and str(capability_id or "").strip().lower() in {
            "approval_read", "approval", "approvals", APPROVAL_PROCESS_CAPABILITY_ID,
        }
        and not candidate_plan
        and not query_intent
        and not unsupported_criteria
        and not missing_fields
    ):
        recovered_process = recover_approval_process_action(message)
        if recovered_process is not None:
            # The explicit owner or history scope belongs to
            # approval_process, whether the model selected the inbox domain
            # or the process domain but omitted the second-stage action.
            # Correct only this registered overlap; do not infer arbitrary
            # approval actions.
            capability_id = "approval_process"
            action_id = recovered_process["action_id"]
            execution_class = recovered_process.get("execution_class") or execution_class
            candidate_plan = dict(recovered_process.get("candidate_plan") or {})
            explicit_candidate_supplied = True
        elif str(capability_id or "").strip().lower() in {
            "approval_read", "approval", "approvals",
        }:
            recovered_approval = recover_approval_read_action(message)
            if recovered_approval is not None:
                action_id = recovered_approval["action_id"]
                execution_class = recovered_approval.get("execution_class") or execution_class
                candidate_plan = dict(recovered_approval.get("candidate_plan") or {})
                query_intent = dict(recovered_approval.get("query_intent") or {}) or query_intent
                explicit_candidate_supplied = True

    inferred_workflow = infer_workflow_capability(candidate_plan)
    if inferred_workflow and (not execution_class or execution_class == "workflow"):
        execution_class = "workflow"
    if (not capability_id or str(capability_id).strip() in {"general_agent", "general"}) and execution_class == "workflow":
        capability_id = inferred_workflow
    # Typed read plans produced by the route adapter have an unambiguous
    # action even when a provider omitted the redundant action_id envelope.
    # This is not operation-only model compatibility: these branches are
    # bounded by the already selected domain and execution class.
    if not action_id:
        if capability_id == "approval_read" and query_intent is not None:
            action_id = "approval.read.pending"
        elif capability_id == "schedule" and execution_class == "metadata_query":
            action_id = "schedule.query"
        elif capability_id == "party_file" and execution_class == "metadata_query":
            operation_hint = str((candidate_plan or {}).get("operation") or "").upper()
            action_id = "party_file.attachments" if operation_hint in {"ATTACHMENTS", "ATTACHMENT"} else "party_file.metadata"
        elif execution_class in {"metadata_query", "approval_query", "report"}:
            typed_read_action = resolve_typed_read_action(
                capability_id,
                execution_class,
                candidate_plan=candidate_plan,
                query_intent=query_intent,
            )
            if typed_read_action is not None:
                capability_id = typed_read_action.capability_id
                action_id = typed_read_action.action_id
                execution_class = typed_read_action.execution_class
                candidate_plan = {
                    **(query_intent or {}),
                    **(candidate_plan or {}),
                    "action_id": typed_read_action.action_id,
                    "operation": typed_read_action.operation,
                }
    typed_action = _infer_typed_action_from_shape(
        capability_id, execution_class, candidate_plan, query_intent, message
    )
    if typed_action and not action_id:
        typed_capability, typed_action_id, typed_class = typed_action
        capability_id = typed_capability
        action_id = typed_action_id
        execution_class = typed_class
        candidate_plan = {
            **(candidate_plan or {}),
            "action_id": typed_action_id,
            "_action_id_synthesized": True,
        }
        # A typed approval list/rank payload can be normalized into the
        # canonicalizer's vocabulary without asking the model for a second
        # free-form decision.
        if typed_action_id == "approval.read.pending" and query_intent is None:
            raw_sorts = (candidate_plan or {}).get("sort") or []
            normalized_sorts = []
            for item in raw_sorts:
                if not isinstance(item, dict):
                    continue
                field = {"createTime": "created_time", "create_time": "created_time"}.get(
                    str(item.get("field") or ""), str(item.get("field") or "")
                )
                direction = str(item.get("direction") or item.get("order") or "DESC").upper()
                normalized_sorts.append({"field": field, "direction": direction})
            query_intent = {
                "entity": "pending_approval",
                "operation": "rank" if normalized_sorts else "list",
                "sort": normalized_sorts,
                "limit": (candidate_plan or {}).get("limit"),
            }
    proposed_operation = str(
        (candidate_plan or {}).get("operation")
        or (candidate_plan or {}).get("action")
        or (query_intent or {}).get("operation")
        or (query_intent or {}).get("action")
        or ""
    ).strip() or None
    action_id_was_explicit = bool(action_id)
    selected_action = resolve_action(capability_id, action_id, proposed_operation)
    if canonical_capability_id(capability_id) == "meeting":
        recovered_meeting_action = recover_meeting_write_action(
            message, selected_action.action_id if selected_action is not None else action_id
        )
        if recovered_meeting_action and recovered_meeting_action != action_id:
            previous_action_id = action_id
            action_id = recovered_meeting_action
            selected_action = resolve_action(capability_id, action_id)
            action_recovery = {
                "from": str(previous_action_id or ""),
                "to": recovered_meeting_action,
                "reason": "explicit_meeting_write_boundary",
            }
    if selected_action is not None:
        if not action_id_was_explicit and proposed_operation:
            action_recovery = {
                "from": proposed_operation,
                "to": selected_action.action_id,
                "reason": "registered_operation_alias",
            }
        action_id = selected_action.action_id
        execution_class = selected_action.execution_class
        candidate_plan = {
            **(candidate_plan or {}),
            "action_id": selected_action.action_id,
            "operation": selected_action.operation,
        }
        candidate_plan, query_intent = _normalize_action_field_aliases(
            selected_action.action_id, candidate_plan, query_intent
        )
        candidate_plan = _recover_explicit_reference_fields(
            selected_action.action_id, message, candidate_plan
        )
        if selected_action.action_id == "meeting.query":
            normalized_meeting = normalize_meeting_query_candidate(
                message, candidate_plan, query_intent
            )
            if normalized_meeting is not None:
                candidate_plan = normalized_meeting
        if selected_action.action_id == "schedule.query":
            original_candidate = dict(candidate_plan)
            normalized_schedule = normalize_schedule_query_candidate(
                message, candidate_plan, query_intent
            )
            if normalized_schedule is not None:
                candidate_plan = normalized_schedule
                if candidate_plan != original_candidate:
                    schedule_date_recovery = {
                        "reason": "server_business_clock",
                        "actionId": selected_action.action_id,
                    }
        if not action_id_was_explicit:
            candidate_plan["_action_id_synthesized"] = True
        explicit_candidate_supplied = True
    elif action_id:
        # Keep the invalid action visible to the compiler as a structured
        # unsupported action; never silently turn it into a generic fallback.
        candidate_plan = {**(candidate_plan or {}), "action_id": action_id}
        explicit_candidate_supplied = True
    decision = resolve_capability(
        capability_id if capability_routing_enabled() else None,
        strategy if capability_routing_enabled() else None,
        confidence if capability_routing_enabled() else None,
        unsupported_criteria if capability_routing_enabled() else None,
        missing_fields if capability_routing_enabled() else None,
    )
    action_selection_required = (
        decision["capabilityId"] != "general_agent"
        and not confirmation_intent
        and selected_action is None
        and not action_id
        and not unsupported_criteria
        and not missing_fields
        and party_file_attachment is None
    )
    # ``recover_meeting_write_action`` 只负责阻止“预约”误路由为会议查询，不能
    # 代替模型完成正式动作选择或从自然语言摘取业务字段。若模型首轮只交了领域，
    # 服务端虽然可以给出 ``meeting.create`` 的建议，但必须回到受限 Action Catalog
    # 让模型显式提交 action_id 与 candidate_plan。否则“项目例会”等已给字段只会
    # 停留在文本中，后续 PendingPlan 无法恢复。
    recovered_meeting_action_needs_selection = (
        action_recovery is not None
        and action_recovery.get("reason") == "explicit_meeting_write_boundary"
        and decision["capabilityId"] == "meeting"
        and not action_id_was_explicit
        and not model_supplied_candidate_plan
        and not query_intent
        and _meeting_write_contains_explicit_field_signal(message)
    )
    if recovered_meeting_action_needs_selection:
        action_selection_required = True
    if action_selection_required:
        decision["strategy"] = "clarify"
    # A malformed provider tool call may omit all routing arguments (or leave
    # the generic ``content_search`` class behind).  Recover only the narrow,
    # unambiguous structured metadata case; every other unknown request keeps
    # the general-agent fallback and never gets forced into a business path.
    fallback_plan = party_metadata_fallback_plan(message)
    if fallback_plan is not None and decision["capabilityId"] == "general_agent":
        capability_id = fallback_plan["capability_id"]
        execution_class = fallback_plan["execution_class"]
        candidate_plan = fallback_plan["candidate_plan"]
        decision = resolve_capability(capability_id, "direct", 0.9)
    meeting_fallback_plan = meeting_metadata_fallback_plan(message)
    if meeting_fallback_plan is not None and decision["capabilityId"] == "general_agent":
        capability_id = meeting_fallback_plan["capability_id"]
        execution_class = meeting_fallback_plan["execution_class"]
        candidate_plan = meeting_fallback_plan["candidate_plan"]
        decision = resolve_capability(capability_id, "direct", 0.9)
    schedule_fallback_plan = schedule_metadata_fallback_plan(message) if provider_schedule_envelope_missing else None
    if schedule_fallback_plan is not None and decision["capabilityId"] == "general_agent":
        capability_id = schedule_fallback_plan["capability_id"]
        execution_class = schedule_fallback_plan["execution_class"]
        candidate_plan = schedule_fallback_plan["candidate_plan"]
        decision = resolve_capability(capability_id, "direct", 0.9)
    query_resolution = None
    if decision["capabilityId"] == "approval_read" and query_intent is not None:
        query_resolution = canonicalize_approval_query(query_intent)
        if query_resolution.status == "CLARIFY":
            decision["strategy"] = "clarify"
    # 候选引用的 UPDATE/CANCEL 先转换为 Java 定向核验计划。它是代码签发的
    # ``RESOLVED`` 只读 WorkOrder，不会把 source_*_id 注入写 candidate_plan。
    # 核验回执后的二次编译由 TargetResolutionMiddleware 完成。
    resolution_route = None
    if (
        trusted_context_candidate
        and context_intent == "REFER_TO_QUERY_CANDIDATE"
        and target_resolution is not None
        and action_id in {"schedule.update", "schedule.cancel", "meeting.update", "meeting.cancel"}
    ):
        resolution_route = target_resolution_compiled_route(
            capability_id=str(decision["capabilityId"]),
            action_id=str(action_id),
            candidate_plan=candidate_plan or {},
            target_resolution=target_resolution,
        )
    compiled_plan = None
    if not confirmation_intent and resolution_route is None:
        compiled_plan = compile_plan(
            capability_id=decision["capabilityId"],
            execution_class=execution_class,
            candidate_plan=candidate_plan,
            query_intent=query_intent,
        )
    if compiled_plan is not None:
        if compiled_plan.status == "RESOLVED":
            decision["strategy"] = "direct"
        elif compiled_plan.status in {"CLARIFY", "UNSUPPORTED"}:
            decision["strategy"] = "clarify"
        elif query_resolution is not None and query_resolution.status in {"INVALID", "UNSUPPORTED"}:
            decision["strategy"] = "clarify"
        compiled_action_id = str(
            ((compiled_plan.canonical or {}).get("action_id"))
            or ((compiled_plan.canonical or {}).get("actionId"))
            or ""
        ).strip()
        if compiled_action_id and not action_id:
            # Recovery and typed-read compilation can resolve a canonical
            # action after the model omitted the redundant envelope field.
            # Promote that compiler-owned identity back to the route result so
            # execution, audit, and routingTrace share the same action fact.
            action_id = compiled_action_id
    # The main Agent supplies this two-value performance classification. The
    # router only normalizes it; safety floors in set_route_reasoning_policy
    # can still raise a simple label to low for writes or confirmations.
    route.task_complexity = task_complexity
    route.reasoning_effort = "off" if task_complexity == "simple" else "low"
    route.capability_id = decision["capabilityId"]
    route.strategy = decision["strategy"]
    route.execution_class = compiled_plan.execution_class if compiled_plan is not None else execution_class
    route.confidence = decision["confidence"]
    route.missing_fields = [str(value).strip() for value in (missing_fields or []) if str(value).strip()]
    route.unsupported_criteria = decision["unsupportedCriteria"]
    # The main Agent calls this Tool before it delegates. Store the validated
    # policy once so every later main/sub-agent model call in this Run shares
    # it without a second LLM classification request.
    set_route_reasoning_policy(route, message)
    result = route.model_dump()
    result["routeDecision"] = decision
    if resolution_route is not None:
        result.update(resolution_route)
        result["routeDecision"]["executionTool"] = resolution_route["executionTool"]
        result["routeDecision"]["actionId"] = resolution_route["actionId"]
        result["routeDecision"]["strategy"] = "direct"
        result["targetResolution"] = True
    if action_recovery is not None:
        result["routeDecision"]["actionRecovery"] = action_recovery
        result["actionRecovery"] = action_recovery
    if action_id:
        result["routeDecision"]["actionId"] = action_id
        result["actionId"] = action_id
    if schedule_date_recovery is not None:
        result["routeDecision"]["scheduleDateRecovery"] = schedule_date_recovery
        result["scheduleDateRecovery"] = schedule_date_recovery
    if action_selection_required:
        result["routePhase"] = "ACTION_SELECTION"
        result["planStatus"] = "CLARIFY"
        result["actionSelection"] = {
            "required": True,
            "capabilityId": decision["capabilityId"],
            "catalog": action_catalog_prompt(decision["capabilityId"]),
            # Preserve typed values extracted during a provider retry.  The
            # next routing call must add only ``action_id`` and may reuse this
            # payload; dropping it was causing repeated route calls and made
            # the model fall back to the generic task tool.
            # 对仅凭自然语言恢复的会议写动作，不能把服务端加上的
            # action_id/operation 伪装成模型已经提交的候选计划。
            "candidatePlan": (
                {} if recovered_meeting_action_needs_selection else candidate_plan or {}
            ),
            "queryIntent": query_intent or {},
            "requiresStructuredSubmission": recovered_meeting_action_needs_selection,
            "nextRequiredFields": ["action_id"],
            "actions": [
                {
                    "actionId": item.action_id,
                    "label": action_description(item),
                    "executionClass": action_execution_class(item),
                    "readOnly": action_read_only(item),
                    "requiresConfirmation": action_requires_confirmation(item),
                    "requiredFields": list(action_required_fields(item)),
                    "fields": [
                        {
                            "name": field.name,
                            "type": field.field_type,
                            "required": field.required,
                            "nullable": field.nullable,
                            "description": field.description,
                            "sourcePolicy": field.source_policy,
                        }
                        for field in action_field_specs(item)
                    ],
                }
                for item in actions_for_capability(decision["capabilityId"])
            ],
        }
        result["clarification"] = {
            "status": "ACTION_SELECTION",
            "question": "请从当前领域动作目录中选择一个具体业务动作。",
            "issues": [],
            "missingFields": ["action_id"],
            "nextRequiredFields": ["action_id"],
            # 动词纠偏只能提供“建议动作”，不能跳过二阶段 schema 校验；模型仍须
            # 从 actions 枚举显式选择并提交自己的结构化 candidate_plan。
            "suggestedActionId": (
                action_id if recovered_meeting_action_needs_selection else
                _suggest_action_id_from_payload(
                    decision["capabilityId"], candidate_plan, query_intent
                )
            ),
            "options": result["actionSelection"]["actions"],
        }
    if confirmation_intent:
        # Do not expose an executor or a synthetic action id.  A valid
        # ApprovalCard resume is handled by the graph's interrupt/resume
        # boundary; a free-form confirmation only receives this safe
        # clarification when no such card is present in the current run.
        result["planStatus"] = "CLARIFY"
        result["clarification"] = {
            "status": "CLARIFY",
            "question": "请点击当前党务文件确认卡完成发布，不能通过普通文本直接提交。",
            "issues": ["普通文本确认不能替代党务文件 ApprovalCard"],
            "missingFields": [],
        }
    if compiled_plan is not None:
        result["plan"] = compiled_plan.model_dump(mode="json")
        result["planStatus"] = compiled_plan.status
        if compiled_plan.execution_tool:
            result["routeDecision"]["executionTool"] = compiled_plan.execution_tool
            result["executionTool"] = compiled_plan.execution_tool
            result["executionPlan"] = compiled_plan.canonical
            result["planId"] = compiled_plan.plan_id
        # The action-catalog clarification is the higher-level contract when
        # an approval-process route has no action_id at all.  Do not let the
        # domain compiler's lower-level wording overwrite that stable choice;
        # otherwise the UI reports a different question than the action
        # selection payload exposes.
        if compiled_plan.status in {"CLARIFY", "UNSUPPORTED"} and not action_selection_required:
            result["clarification"] = {
                "status": compiled_plan.status,
                "question": compiled_plan.clarification_question or "请补充或确认这项任务的查询条件。",
                "issues": compiled_plan.issues,
                "missingFields": compiled_plan.missing_fields,
            }
    if query_resolution is not None:
        result["queryResolution"] = query_resolution.model_dump(mode="json", by_alias=True)
        if query_resolution.status == "RESOLVED" and query_resolution.plan is not None:
            # The rule layer owns execution semantics. Once resolved, the
            # model must not choose among overlapping list/search/analyze
            # tools or change the operation order on a retry.
            execution_plan = query_resolution.plan.model_dump(mode="json")
            result["routeDecision"]["executionTool"] = "run_approval_query_plan"
            result["routeDecision"]["executionPlan"] = execution_plan
            result["executionTool"] = "run_approval_query_plan"
            result["executionPlan"] = execution_plan
        elif query_resolution.status in {"CLARIFY", "INVALID", "UNSUPPORTED"}:
            result["clarification"] = {
                "status": query_resolution.status,
                "question": query_resolution.clarification_question or "请补充或确认审批查询条件。",
                "issues": query_resolution.issues,
                "options": query_resolution.alternatives,
            }
    if party_file_attachment and party_file_attachment.get("status") == "CLARIFY":
        result["clarification"] = {
            "status": "CLARIFY",
            "question": party_file_attachment["message"],
            "issues": ["source_party_file_id"],
            "missingFields": ["source_party_file_id"],
            "options": party_file_attachment.get("options", []),
        }
    try:
        writer = get_stream_writer()
    except RuntimeError:
        writer = None
    if writer is not None:
        emit(
            writer,
            "route.selected",
            f"已选择能力 {decision['capabilityId']}，执行策略为 {decision['strategy']}",
            capabilityId=decision["capabilityId"],
            actionId=action_id,
            strategy=decision["strategy"],
            confidence=decision["confidence"],
            missingFields=decision["missingFields"],
            unsupportedCriteria=decision["unsupportedCriteria"],
        )
        if compiled_plan is not None:
            emit(
                writer,
                "plan.compiled",
                f"已编译任务计划：{compiled_plan.status}",
                planId=compiled_plan.plan_id,
                planStatus=compiled_plan.status,
                capabilityId=compiled_plan.capability_id,
                executionClass=compiled_plan.execution_class,
                executionTool=compiled_plan.execution_tool,
                issues=compiled_plan.issues,
            )
    presentation = None
    if action_selection_required:
        presentation = {
            "blockType": "card",
            "cardType": "clarification",
            "resultKind": "clarification",
            "summary": {"headline": "请先选择具体业务动作"},
            "actions": result["actionSelection"]["actions"],
        }
    elif confirmation_intent:
        presentation = {
            "blockType": "card",
            "cardType": "clarification",
            "resultKind": "clarification",
            "summary": {"headline": "请使用党务文件确认卡完成发布"},
            "actions": [],
        }
    elif query_resolution is not None and query_resolution.status in {"CLARIFY", "INVALID", "UNSUPPORTED"}:
        presentation = {
            "blockType": "card",
            "cardType": "clarification",
            "resultKind": "clarification",
            "summary": {"headline": "需要确认审批查询口径"},
            "actions": query_resolution.alternatives,
        }
    elif party_file_attachment and party_file_attachment.get("status") == "CLARIFY":
        presentation = {
            "blockType": "card",
            "cardType": "clarification",
            "resultKind": "clarification",
            "summary": {"headline": "请先选择要核对附件的党务文件"},
            "actions": party_file_attachment.get("options", []),
        }
    if confirmation_intent:
        result["routeState"] = "CONFIRMATION_REQUIRED"
    elif action_selection_required:
        result["routeState"] = "ACTION_SELECTION"
    elif query_resolution is not None and query_resolution.status in {"INVALID", "UNSUPPORTED"}:
        result["routeState"] = "UNSUPPORTED" if query_resolution.status == "UNSUPPORTED" else "FIELD_CLARIFICATION"
    elif query_resolution is not None and query_resolution.status == "CLARIFY":
        result["routeState"] = "FIELD_CLARIFICATION"
    elif compiled_plan is not None:
        result["routeState"] = {
            "RESOLVED": "RESOLVED",
            "CLARIFY": "FIELD_CLARIFICATION",
            "UNSUPPORTED": "UNSUPPORTED",
            "FALLBACK": "FALLBACK",
        }.get(compiled_plan.status, "FALLBACK")
    elif result.get("clarification"):
        result["routeState"] = "FIELD_CLARIFICATION"
    else:
        result["routeState"] = "FALLBACK"
    catalog_meta = runtime_action_catalog_meta() or {}
    model_trace = current_model_trace(str(current_agent_context().get("runId") or ""))
    trace_capability_id = decision.get("capabilityId") or result.get("capability_id")
    trace_action_id = (
        action_id
        or (decision.get("actionId") if isinstance(decision, dict) else None)
        or ((compiled_plan.canonical if compiled_plan is not None else {}) or {}).get("action_id")
        or ((compiled_plan.canonical if compiled_plan is not None else {}) or {}).get("actionId")
    )
    result["routingTrace"] = {
        "model_id": model_trace.get("model_id") or "runtime-resolved",
        # 推理实验仅影响模型供应商的规划预算。把实际取值写入 trace，供离线评测
        # 比较，不得把它当作权限、计划或审批卡的放行条件。
        "requested_reasoning_effort": model_trace.get("requested_reasoning_effort"),
        "effective_reasoning_effort": model_trace.get("effective_reasoning_effort"),
        "reasoning_experiment_eligible": model_trace.get("reasoning_experiment_eligible"),
        "reasoning_experiment_enabled": model_trace.get("reasoning_experiment_enabled"),
        "prompt_version": PROMPT_VERSION,
        "catalog_version": catalog_meta.get("contractVersion") or "agent-actions-v1",
        "skill_version": skill_registry.version_for(trace_capability_id, action_id=action_id),
        "plan_revision": (
            (candidate_plan or {}).get("plan_revision")
            or (candidate_plan or {}).get("planRevision")
        ),
        "capability_id": trace_capability_id,
        "action_id": trace_action_id,
        "requested_action_id": requested_action_id,
    }
    return tool_success(result, presentation)
