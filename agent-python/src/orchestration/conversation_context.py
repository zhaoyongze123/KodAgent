"""多轮对话上下文候选的构建、校验和提示词投影。

文件职责
========
本模块位于 DeepAgents/LangGraph checkpoint 与业务路由之间。它不执行工具、
不调用 Java，也不产生业务执行权；它只把当前 Thread 中已有的受限状态压缩为
候选清单，帮助主 Agent 判断短句、指代或补充信息是否在续接某项任务。

调用链
========
``ContextCandidateMiddleware`` 在模型调用前扫描 checkpoint：

* ``PendingPlan`` 形成待补字段候选；
* 会议、个人日程和项目列表查询 ToolMessage 形成最小化的定位候选；
* ``conversation_context_prompt`` 仅把脱敏摘要交给规划阶段模型；
* ``PlanToolProjectionMiddleware`` 在路由工具调用边界验证候选 ID，只签发
  Java 定向核验请求；核验成功后中央编译器才重新生成写计划。

这里的候选是“理解线索”，不是授权事实。真正的可编辑性和对象状态仍由后续
Java 门面与工作流重新校验。
"""

from __future__ import annotations

import json
import logging
import hmac
import hashlib
import os
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, NotRequired

from langchain.agents.middleware import AgentMiddleware, AgentState
from pydantic import BaseModel, ConfigDict, Field

from ..tools.common.events import current_agent_context
from .delegated_receipt import model_visible_delegated_receipt, parse_execution_receipt
from .domain_dispatch import parse_work_order
from .route_state import message_content, message_name, message_type


# ``authorized_query`` 表示 Java 只读查询投影；``authorized_resource`` 表示
# 已确认写入后的 Java 正式对象。两者都只是下一轮“找对象”的线索，绝不是直接
# 写入授权；分开保留可兼容已有 checkpoint 与审计语义。
ContextCandidateKind = Literal[
    "pending_plan", "pending_approval", "authorized_resource", "authorized_query",
]
ContextIntent = Literal[
    "NEW_REQUEST",
    "RESUME_PENDING_PLAN",
    "REFER_TO_QUERY_CANDIDATE",
    "LOCATE_APPROVAL_CARD",
    "AMBIGUOUS",
]

_CANDIDATE_TTL = timedelta(minutes=15)
_MAX_CANDIDATES = 8
_RECENT_MESSAGE_WINDOW = 4
# 最近两次用户续接可以把候选内部 ID 作为“定向读取定位器”。超过该窗口，候选
# 仍可进入提示词帮助理解标题/时间，但不能省掉受限查询步骤，避免旧对象被误操作。
_DIRECT_LOOKUP_MAX_TURN_DISTANCE = 2
_LOG = logging.getLogger(__name__)
# 生产应配置稳定密钥，保证进程重启后的短期 checkpoint 仍可恢复。本地未配置时
# 使用仅进程内有效的随机密钥，候选失效后会自然降级为重新查询或澄清。
_PROOF_SECRET = os.getenv("OA_AGENT_CONTEXT_CANDIDATE_SECRET", "").encode("utf-8") or secrets.token_bytes(32)


def context_shadow_mode() -> bool:
    """返回是否只观察不采用候选。

    Shadow 模式仍会生成候选和日志，但计划投影层不会注入任何来源字段。它用于
    对照真实对话中的候选推荐与用户最终选择，确认误关联率后再打开正式采用。
    """

    return os.getenv("OA_AGENT_CONTEXT_SHADOW_MODE", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


class ContextCandidate(BaseModel):
    """一个仅在当前身份和 Thread 内有效的上下文候选。

    参数说明：
        candidate_id：服务端随机生成的引用；模型只能选择已有值，不能通过它
            构造新的业务对象。
        kind：候选来源类型。``authorized_query`` 表示 Java 查询结果；
            ``authorized_resource`` 表示 Java 已确认写入的正式对象。
        summary：允许注入模型的最小化中文摘要，不含完整响应或内部授权字段。
        trusted_plan：仅供计划投影层发起定向 Java 核验的内部定位字段，绝不直接
            注入提示词或写操作计划。
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")

    candidate_id: str = Field(alias="candidateId", min_length=16, max_length=128)
    kind: ContextCandidateKind
    capability_id: str = Field(alias="capabilityId", min_length=1, max_length=64)
    action_ids: tuple[str, ...] = Field(alias="actionIds", default=())
    summary: str = Field(min_length=1, max_length=400)
    status: str = Field(min_length=1, max_length=64)
    issued_at: datetime = Field(alias="issuedAt")
    expires_at: datetime = Field(alias="expiresAt")
    scope: dict[str, str] = Field(default_factory=dict)
    source_tool_call_id: str | None = Field(alias="sourceToolCallId", default=None)
    source_turn: int = Field(alias="sourceTurn", default=0, ge=0)
    trusted_plan: dict[str, Any] = Field(alias="trustedPlan", default_factory=dict)


class ContextCandidateState(AgentState):
    """写入 LangGraph checkpoint 的候选状态，不能由模型工具参数直接修改。"""

    context_candidates: NotRequired[list[dict[str, Any]]]
    # 这不是业务事实或用户画像，仅保留本 Thread 的候选构建诊断，便于回放
    # “为什么出现/没有出现某个候选”。最多保存最近 40 条，避免 checkpoint 无限增长。
    context_audit: NotRequired[list[dict[str, Any]]]


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _scope() -> dict[str, str]:
    """读取当前运行身份；空值保留以兼容本地控制台。"""

    context = current_agent_context()
    return {
        key: str(context.get(key) or "").strip()
        for key in ("tenantId", "userId", "threadId")
    }


def _scope_matches(candidate: ContextCandidate) -> bool:
    """候选只能在签发它的身份和 Thread 中使用。"""

    current = _scope()
    for key, value in candidate.scope.items():
        if value and current.get(key) and value != current.get(key):
            return False
    return True


def _as_candidates(value: Any) -> list[ContextCandidate]:
    candidates: list[ContextCandidate] = []
    for raw in value if isinstance(value, list) else []:
        try:
            candidate = ContextCandidate.model_validate(raw)
        except (TypeError, ValueError):
            continue
        if candidate.expires_at > datetime.now(UTC) and _scope_matches(candidate):
            candidates.append(candidate)
    return candidates


def _new_candidate(
    *,
    kind: ContextCandidateKind,
    capability_id: str,
    action_ids: tuple[str, ...],
    summary: str,
    status: str,
    trusted_plan: dict[str, Any] | None = None,
    source_tool_call_id: str | None = None,
    source_turn: int = 0,
) -> ContextCandidate:
    now = datetime.now(UTC)
    return ContextCandidate(
        candidateId=secrets.token_urlsafe(18),
        kind=kind,
        capabilityId=capability_id,
        actionIds=action_ids,
        summary=summary,
        status=status,
        issuedAt=now,
        expiresAt=now + _CANDIDATE_TTL,
        scope=_scope(),
        sourceToolCallId=source_tool_call_id,
        sourceTurn=source_turn,
        trustedPlan=dict(trusted_plan or {}),
    )


def _pending_candidate(value: Any, *, source_turn: int) -> ContextCandidate | None:
    if not isinstance(value, dict):
        return None
    plan_id = str(value.get("planId") or "").strip()
    capability_id = str(value.get("capabilityId") or "").strip()
    action_id = str(value.get("actionId") or "").strip()
    missing = [str(item) for item in value.get("missingFields") or [] if str(item).strip()]
    if not (plan_id and capability_id and action_id and missing):
        return None
    return _new_candidate(
        kind="pending_plan",
        capability_id=capability_id,
        action_ids=(action_id,),
        summary=f"待补充的{capability_id}计划：仍缺少 {', '.join(missing)}。",
        status="PENDING_FIELDS",
        trusted_plan={"planId": plan_id},
        source_turn=source_turn,
    )


def _tool_response_data(message: Any) -> Any:
    """读取统一 ToolResponse 的 data 字段，解析失败时视为无投影。"""

    response = _as_dict(message_content(message))
    if response.get("ok") is not True:
        return None
    return response.get("data")


def _message_tool_calls(message: Any) -> list[dict[str, Any]]:
    """读取模型消息中的工具调用，兼容 LangChain 对象与 checkpoint 字典。"""

    value = message.get("tool_calls") if isinstance(message, dict) else getattr(message, "tool_calls", None)
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _delegated_executor_result(
    message: Any,
    *,
    executor_tool: str,
    messages: list[Any],
    message_index: int,
) -> tuple[Any, str | None] | None:
    """从受控 ``task`` 回执恢复子 Agent 查询结果。

    主图委托后，真正的 ``get_my_calendar`` 等工具消息留在子 Agent 图内；主图
    只能看到名为 ``task`` 的回执。因此这里不能再按工具名直接识别，而必须同时
    校验三件事：回执是结构化成功回执、其 executor 与目标查询工具相同、以及
    对应的父级 task 调用中确实携带了同一份 WorkOrder。这样子 Agent 的自然语言
    回复或伪造的 JSON 都不能成为后续写操作的授权来源。
    """

    if message_type(message) != "tool" or message_name(message) != "task":
        return None
    receipt = parse_execution_receipt(message_content(message))
    if (
        receipt is None
        or receipt.status != "SUCCEEDED"
        or receipt.executor_tool != executor_tool
        or receipt.result is None
    ):
        return None
    tool_call_id = str(
        message.get("tool_call_id") if isinstance(message, dict) else getattr(message, "tool_call_id", "")
    ).strip()
    if not tool_call_id:
        return None
    # 只接受与当前 task 回执一一对应、且由主图编译器签发的 WorkOrder。
    for previous in reversed(messages[:message_index]):
        for call in _message_tool_calls(previous):
            if str(call.get("id") or "").strip() != tool_call_id or str(call.get("name") or "") != "task":
                continue
            args = call.get("args")
            description = args.get("description") if isinstance(args, dict) else ""
            work_order = parse_work_order(str(description or ""))
            if (
                work_order is not None
                and work_order.plan_id == receipt.plan_id
                and work_order.execution_tool == executor_tool
            ):
                # 主图目前为同一领域复用稳定的 task 调用名。不能只用该 ID 做
                # checkpoint 去重，否则后一份已编译查询会被误认成旧结果；计划
                # ID 是中央编译为每次委托签发的唯一事实，因此组成证据键。
                return receipt.result, f"{tool_call_id}:{receipt.plan_id}"
            return None
    return None


def _executor_result_data(
    message: Any,
    *,
    executor_tool: str,
    messages: list[Any] | None = None,
    message_index: int | None = None,
) -> tuple[Any, str | None] | None:
    """统一读取主图直调或已验证子 Agent 回执中的真实执行结果。"""

    if message_type(message) != "tool":
        return None
    if message_name(message) == executor_tool:
        data = _tool_response_data(message)
        if data is None:
            return None
        source_tool_call_id = str(
            message.get("tool_call_id") if isinstance(message, dict) else getattr(message, "tool_call_id", "")
        ).strip() or None
        return data, source_tool_call_id
    if messages is not None and message_index is not None:
        return _delegated_executor_result(
            message,
            executor_tool=executor_tool,
            messages=messages,
            message_index=message_index,
        )
    return None


def _candidate_source_key(message: Any, *, messages: list[Any], message_index: int) -> str | None:
    """返回当前消息的候选证据键，用于增量扫描而非业务对象身份。"""

    if message_type(message) != "tool":
        return None
    tool_name = message_name(message)
    if tool_name in {
        "list_my_meeting_bookings", "get_my_meeting_booking", "get_my_calendar",
        "confirm_personal_schedule",
    }:
        return str(
            message.get("tool_call_id") if isinstance(message, dict) else getattr(message, "tool_call_id", "")
        ).strip() or None
    if tool_name == "task":
        receipt = parse_execution_receipt(message_content(message))
        if receipt is None or receipt.executor_tool not in {
            "list_my_meeting_bookings", "get_my_meeting_booking", "get_my_calendar",
        }:
            return None
        result = _delegated_executor_result(
            message,
            executor_tool=receipt.executor_tool,
            messages=messages,
            message_index=message_index,
        )
        return result[1] if result is not None else None
    return None


def _rows(value: Any) -> list[dict[str, Any]]:
    """兼容 Java 常见列表信封，但只接受字典行。"""

    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    for key in ("list", "items", "records", "rows", "data"):
        nested = value.get(key)
        if isinstance(nested, list):
            return [dict(item) for item in nested if isinstance(item, dict)]
    return []


def _meeting_candidates(
    message: Any,
    *,
    source_turn: int,
    messages: list[Any] | None = None,
    message_index: int | None = None,
) -> list[ContextCandidate]:
    """把会议查询的可编辑记录压缩为后续修改/取消可引用的候选。"""

    result = _executor_result_data(
        message, executor_tool="list_my_meeting_bookings", messages=messages, message_index=message_index,
    )
    if result is None:
        return []
    data, source_tool_call_id = result
    candidates: list[ContextCandidate] = []
    for row in _rows(data):
        booking_id = row.get("bookingId")
        if booking_id is None or row.get("editable") is not True:
            continue
        subject = str(row.get("subject") or "未命名会议").strip()[:100]
        start = str(row.get("startTime") or "").strip()[:32]
        end = str(row.get("endTime") or "").strip()[:32]
        time_text = " 至 ".join(item for item in (start, end) if item) or "时间待确认"
        candidates.append(
            _new_candidate(
                kind="authorized_query",
                capability_id="meeting",
                action_ids=("meeting.update", "meeting.cancel"),
                summary=f"可编辑会议预约：{subject}，{time_text}。",
                status="QUERY_CANDIDATE",
                trusted_plan={
                    "source_booking_id": int(booking_id),
                    "_authorized_source_fields": ["source_booking_id"],
                },
                source_tool_call_id=source_tool_call_id,
                source_turn=source_turn,
            )
        )
        if len(candidates) >= _MAX_CANDIDATES:
            break
    return candidates


def _project_candidates(
    message: Any,
    *,
    source_turn: int,
    messages: list[Any] | None = None,
    message_index: int | None = None,
) -> list[ContextCandidate]:
    """把当前用户可访问的项目列表压缩为后续指代的定位候选。

    项目候选只能解决“就这个项目”中的对象指代，不授予项目数据访问权。后续
    ``project.investigate`` 等动作仍会由 Java Project Provider 重新校验当前
    KodCloud 成员关系、任务隐私和文件权限。
    """

    result = _executor_result_data(
        message,
        executor_tool="list_accessible_projects",
        messages=messages,
        message_index=message_index,
    )
    if result is None:
        return []
    data, source_tool_call_id = result
    candidates: list[ContextCandidate] = []
    for row in _rows(data):
        project_id = row.get("projectID") or row.get("projectId") or row.get("project_id")
        if project_id is None or isinstance(project_id, bool):
            continue
        project_id = str(project_id).strip()
        if not project_id:
            continue
        name = str(row.get("name") or "未命名项目").strip()[:120]
        description = str(row.get("description") or "").strip().replace("\n", " ")[:160]
        summary = f"可访问项目：{name}" + (f"。{description}" if description else "。")
        candidates.append(
            _new_candidate(
                kind="authorized_query",
                capability_id="project",
                action_ids=(
                    "project.snapshot", "project.tasks", "project.activity",
                    "project.documents", "project.investigate",
                    "project.knowledge.search",
                ),
                summary=summary,
                status="QUERY_CANDIDATE",
                # project_id 只用于定位后续 Java 重新校验的项目，不属于可直接
                # 写入业务计划的 source_*_id，也不会注入模型提示词。
                trusted_plan={"project_id": project_id},
                source_tool_call_id=source_tool_call_id,
                source_turn=source_turn,
            )
        )
        if len(candidates) >= _MAX_CANDIDATES:
            break
    return candidates


def _single_meeting_candidate(
    message: Any,
    *,
    source_turn: int,
    messages: list[Any] | None = None,
    message_index: int | None = None,
) -> ContextCandidate | None:
    """投影已核验的单条会议详情，与会议列表候选使用同一来源字段契约。"""

    result = _executor_result_data(
        message, executor_tool="get_my_meeting_booking", messages=messages, message_index=message_index,
    )
    if result is None:
        return None
    row, source_tool_call_id = result
    if not isinstance(row, dict) or row.get("editable") is not True:
        return None
    booking_id = row.get("bookingId")
    if booking_id is None:
        return None
    subject = str(row.get("subject") or "未命名会议").strip()[:100]
    start = str(row.get("startTime") or "").strip()[:32]
    end = str(row.get("endTime") or "").strip()[:32]
    time_text = " 至 ".join(item for item in (start, end) if item) or "时间待确认"
    return _new_candidate(
        kind="authorized_query",
        capability_id="meeting",
        action_ids=("meeting.update", "meeting.cancel"),
        summary=f"可编辑会议预约：{subject}，{time_text}。",
        status="QUERY_CANDIDATE",
        trusted_plan={
            "source_booking_id": int(booking_id),
            "_authorized_source_fields": ["source_booking_id"],
        },
        source_tool_call_id=source_tool_call_id,
        source_turn=source_turn,
    )


def _schedule_candidates(
    message: Any,
    *,
    source_turn: int,
    messages: list[Any] | None = None,
    message_index: int | None = None,
) -> list[ContextCandidate]:
    """把个人日历中可编辑的 PERSONAL_SCHEDULE 投影为后续写操作候选。"""

    result = _executor_result_data(
        message, executor_tool="get_my_calendar", messages=messages, message_index=message_index,
    )
    if result is None:
        return []
    data, source_tool_call_id = result
    rows = data.get("events") if isinstance(data, dict) else data
    candidates: list[ContextCandidate] = []
    for row in _rows(rows):
        source_id = row.get("sourceId")
        source_type = str(row.get("sourceType") or "").strip().upper()
        if source_id is None or source_type != "PERSONAL_SCHEDULE" or row.get("editable") is not True:
            continue
        title = str(row.get("title") or row.get("subject") or "未命名日程").strip()[:100]
        start = str(row.get("startTime") or "").strip()[:32]
        end = str(row.get("endTime") or "").strip()[:32]
        time_text = " 至 ".join(item for item in (start, end) if item) or "时间待确认"
        candidates.append(
            _new_candidate(
                kind="authorized_query",
                capability_id="schedule",
                action_ids=("schedule.update", "schedule.cancel"),
                summary=f"可编辑个人日程：{title}，{time_text}。",
                status="QUERY_CANDIDATE",
                trusted_plan={
                    "source_schedule_id": int(source_id),
                    "_authorized_source_fields": ["source_schedule_id"],
                },
                source_tool_call_id=source_tool_call_id,
                source_turn=source_turn,
            )
        )
        if len(candidates) >= _MAX_CANDIDATES:
            break
    return candidates


def _confirm_tool_call_args(
    message: Any,
    *,
    messages: list[Any],
    message_index: int,
) -> dict[str, Any]:
    """读取确认工具对应的模型调用参数，仅用于撤销同一草稿的旧卡片候选。

    ``confirm_personal_schedule`` 的成功结果本身不回传 approvalId，不能把任意
    ``pending_approval`` 都清掉。这里必须按 tool_call_id 回溯到同一条 AI 工具调用，
    只取得其 approval_id/draft_id 作生命周期关联，绝不将它们注入模型提示词。
    """

    tool_call_id = str(
        message.get("tool_call_id") if isinstance(message, dict) else getattr(message, "tool_call_id", "")
    ).strip()
    if not tool_call_id:
        return {}
    for previous in reversed(messages[:message_index]):
        for call in _message_tool_calls(previous):
            if str(call.get("id") or "").strip() != tool_call_id:
                continue
            if str(call.get("name") or "").strip() != "confirm_personal_schedule":
                continue
            args = call.get("args")
            return dict(args) if isinstance(args, dict) else {}
    return {}


def _personal_schedule_draft_for_confirmation(
    message: Any,
    *,
    messages: list[Any],
    message_index: int,
) -> dict[str, Any]:
    """返回同一审批草稿的展示字段，不能作为来源 ID 或授权事实使用。

    确认提交 Java 回执只包含 ``scheduleId``。为了让用户可通过“项目周会”等标题
    在多个候选中明确指定对象，这里只从同一 approvalId 的草稿回执读取 title 和
    时间。是否可编辑、正式 ID 与最终版本仍以 Java commit/后续工作流核验为准。
    """

    args = _confirm_tool_call_args(message, messages=messages, message_index=message_index)
    approval_id = str(args.get("approval_id") or args.get("approvalId") or "").strip()
    if not approval_id:
        return {}
    for previous in reversed(messages[:message_index]):
        data = _tool_response_data(previous)
        if not isinstance(data, dict) or data.get("requires_confirmation") is not True:
            continue
        if str(data.get("approvalId") or "").strip() != approval_id:
            continue
        draft = data.get("draft")
        return dict(draft) if isinstance(draft, dict) else {}
    return {}


def _confirmed_personal_schedule_candidate(
    message: Any,
    *,
    source_turn: int,
    messages: list[Any],
    message_index: int,
) -> ContextCandidate | None:
    """把 Java 已提交成功的个人日程投影为后续修改/取消的唯一候选。

    这个函数只接受 ``confirm_personal_schedule`` 的统一成功 ToolResponse。日程
    编号来自 Java commit 的 ``scheduleId``，而不是模型的“创建成功”叙述，也不是
    草稿文本。CREATE 和 UPDATE 成功后该对象仍可被继续维护；CANCEL 成功后对象已
    不存在，不能再生成候选。
    """

    if message_type(message) != "tool" or message_name(message) != "confirm_personal_schedule":
        return None
    result = _tool_response_data(message)
    if not isinstance(result, dict) or result.get("success") is not True:
        return None
    operation = str(result.get("operation") or "").strip().upper()
    schedule_id = result.get("scheduleId")
    if operation not in {"CREATE", "UPDATE"} or schedule_id is None:
        return None
    try:
        source_schedule_id = int(schedule_id)
    except (TypeError, ValueError):
        return None
    if source_schedule_id <= 0:
        return None
    source_tool_call_id = str(
        message.get("tool_call_id") if isinstance(message, dict) else getattr(message, "tool_call_id", "")
    ).strip() or None
    # Java commit 回执只承诺正式 ID 和操作类型。标题/时间只可从同一确认草稿中
    # 回填用于展示与对象指代；目标 ID 仍完全藏在 trusted_plan，模型看不到也不能
    # 伪造。
    draft = _personal_schedule_draft_for_confirmation(
        message, messages=messages, message_index=message_index,
    )
    title = str(draft.get("title") or draft.get("subject") or "").strip()[:100]
    start = str(draft.get("startTime") or draft.get("start_time") or "").strip()[:32]
    end = str(draft.get("endTime") or draft.get("end_time") or "").strip()[:32]
    time_text = " 至 ".join(item for item in (start, end) if item)
    verb = "创建" if operation == "CREATE" else "更新"
    detail = "，".join(item for item in (title, time_text) if item)
    return _new_candidate(
        kind="authorized_resource",
        capability_id="schedule",
        action_ids=("schedule.update", "schedule.cancel"),
        summary=f"刚刚{verb}成功的可编辑个人日程{('：' + detail) if detail else ''}。",
        status="CONFIRMED_RESOURCE",
        trusted_plan={
            "source_schedule_id": source_schedule_id,
            "_authorized_source_fields": ["source_schedule_id"],
        },
        source_tool_call_id=source_tool_call_id,
        source_turn=source_turn,
    )


def _settled_personal_schedule_approval_ids(messages: list[Any]) -> set[str]:
    """返回本 Thread 已成功提交的个人日程审批 ID，用于移除旧确认卡候选。"""

    settled: set[str] = set()
    for message_index, message in enumerate(messages):
        if message_type(message) != "tool" or message_name(message) != "confirm_personal_schedule":
            continue
        result = _tool_response_data(message)
        if not isinstance(result, dict) or result.get("success") is not True:
            continue
        args = _confirm_tool_call_args(message, messages=messages, message_index=message_index)
        approval_id = str(args.get("approval_id") or args.get("approvalId") or "").strip()
        if approval_id:
            settled.add(approval_id)
    return settled


def _party_file_candidate(message: Any, *, source_turn: int) -> ContextCandidate | None:
    """投影 ``get_manage_party_file`` 返回的可编辑党务文件详情。

    该工具本身已由 Java 校验 update/delete 权限；候选只保存受限 source ID，后续
    工作流仍会重新读取文件和版本，避免跨轮使用陈旧快照直接写入。
    """

    if message_type(message) != "tool" or message_name(message) != "get_manage_party_file":
        return None
    row = _tool_response_data(message)
    if not isinstance(row, dict) or row.get("id") is None:
        return None
    source_tool_call_id = str(
        message.get("tool_call_id") if isinstance(message, dict) else getattr(message, "tool_call_id", "")
    ).strip() or None
    title = str(row.get("title") or "未命名党务文件").strip()[:100]
    publish_time = str(row.get("publishTime") or "").strip()[:32]
    return _new_candidate(
        kind="authorized_query",
        capability_id="party_file",
        action_ids=("party_file.update", "party_file.delete", "party_file.attachments"),
        summary=f"可编辑党务文件：{title}{('，' + publish_time) if publish_time else ''}。",
        status="QUERY_CANDIDATE",
        trusted_plan={
            "source_party_file_id": int(row["id"]),
            "_authorized_source_fields": ["source_party_file_id"],
        },
        source_tool_call_id=source_tool_call_id,
        source_turn=source_turn,
    )


def _approval_candidate(message: Any, *, source_turn: int) -> ContextCandidate | None:
    """把已生成的待确认草稿投影为“定位确认卡”候选。

    这里不查询 Java，也不让模型拿到 approvalId/draftId。真正显示或提交确认卡
    仍需前端通过 Java 的 pending-card 接口再次验证 PENDING 状态。本候选的用途
    仅是让“好的/那个草稿”被理解为在回应哪项待确认操作，而不是新建一项写操作。
    """

    if message_type(message) != "tool":
        return None
    data = _tool_response_data(message)
    if not isinstance(data, dict) or data.get("requires_confirmation") is not True:
        return None
    approval_id = str(data.get("approvalId") or "").strip()
    draft_id = str(data.get("draftId") or "").strip()
    if not approval_id or not draft_id:
        return None
    draft = data.get("draft") if isinstance(data.get("draft"), dict) else {}
    subject = str(
        draft.get("subject")
        or draft.get("title")
        or draft.get("name")
        or "待确认操作"
    ).strip()[:100]
    source_tool_call_id = str(
        message.get("tool_call_id") if isinstance(message, dict) else getattr(message, "tool_call_id", "")
    ).strip() or None
    tool = message_name(message) or "业务工作流"
    return _new_candidate(
        kind="pending_approval",
        capability_id="approval",
        action_ids=(),
        summary=f"待确认操作：{subject}（由 {tool} 生成）。",
        status="WAITING_APPROVAL",
        trusted_plan={
            "approval_id": approval_id,
            "draft_id": draft_id,
            "operation_id": str(data.get("operationId") or "").strip(),
        },
        source_tool_call_id=source_tool_call_id,
        source_turn=source_turn,
    )


def _human_turn_count(messages: list[Any]) -> int:
    """计算当前 Thread 的用户回合数，用于候选新鲜度排序而非业务授权。"""

    return sum(1 for message in messages if message_type(message) in {"human", "user"})


def recent_model_messages(messages: list[Any], *, window: int = _RECENT_MESSAGE_WINDOW) -> list[Any]:
    """为模型保留“当前回合 + 最近少量自然对话”的输入窗口。

    这项裁剪只改变本次模型调用看到的消息，不修改 checkpoint。当前回合的工具调用
    必须完整保留，否则 ReAct 无法读取刚返回的路由或执行结果；更早的 ToolMessage
    不再直接混入模型上下文，业务对象只能经候选投影进入提示词。
    """

    items = list(messages or [])
    if not items:
        return []
    current_start = next(
        (index for index in range(len(items) - 1, -1, -1) if message_type(items[index]) in {"human", "user"}),
        len(items),
    )
    if current_start == len(items):
        return items[-window:]
    # 近窗口只保留自然语言消息，避免旧查询结果和内部 ToolMessage 重复占用模型 token。
    # 但 AIMessage 若带有 tool_calls，绝不能单独留下：OpenAI 兼容接口要求其后的
    # 每个调用都有 ToolMessage 回应。旧工具结果既然被裁掉，对应 AIMessage 也必须
    # 同时裁掉，否则下一轮会因“未回应的工具调用”被供应商拒绝。
    recent_history = [
        message for message in items[max(0, current_start - window):current_start]
        if message_type(message) in {"human", "user"}
        or (
            message_type(message) in {"ai", "assistant"}
            and not (
                message.get("tool_calls") if isinstance(message, dict)
                else getattr(message, "tool_calls", None)
            )
        )
    ]
    return [*recent_history, *items[current_start:]]


_MODEL_HIDDEN_SOURCE_KEYS = frozenset({
    # 会议、日程、党务文件的 Java 对象定位字段及其常见传输别名。模型只能经
    # context_candidate_id 选择对象，不能从 ToolMessage 抄写这些值回填写计划。
    "id", "sourceId", "source_id",
    "sourceResultId", "source_result_id", "resultId", "result_id",
    "bookingId", "booking_id", "sourceBookingId", "source_booking_id",
    "scheduleId", "schedule_id", "sourceScheduleId", "source_schedule_id",
    "eventId", "event_id",
    "partyFileId", "party_file_id", "sourcePartyFileId", "source_party_file_id",
    "fileId", "file_id", "documentId", "document_id",
    # RAG 证据的内部定位与排序字段只用于审计、前端引用和离线评测；模型只应
    # 看到 citationId、文件名、章节、版本、受限摘录和召回方式。
    "chunkId", "chunk_id", "projectId", "project_id", "libraryId", "library_id", "ordinal",
    "fusionScore", "fusion_score", "matchedTerms", "matched_terms",
})


def _model_visible_tool_data(value: Any) -> Any:
    """递归移除模型不能作为业务事实使用的对象来源 ID。"""

    if isinstance(value, dict):
        return {
            key: _model_visible_tool_data(item)
            for key, item in value.items()
            if key not in _MODEL_HIDDEN_SOURCE_KEYS
        }
    if isinstance(value, list):
        return [_model_visible_tool_data(item) for item in value]
    return value


def _model_visible_message(message: Any) -> Any:
    """生成业务工具与跨 Agent 回执的模型可见副本。

    ``presentation.sourceResultId`` 是前端更新、去重卡片使用的传输相关键，不是
    checkpoint 候选 ID。把它原样交给模型会让模型误把 ``result:...`` 填进
    ``context_candidate_id``。跨 Agent 的 ``task`` 回执还有另一层边界：原始调查
    结果包含任务树、活动和资料内部编号，只应留在 checkpoint/审计，不应随最终
    总结再次交给主模型。

    此处只复制本次模型调用的 ToolMessage，不修改 checkpoint，所以 UI、审计和
    领域内后续工具调用仍可使用完整事实。
    """

    if message_type(message) != "tool":
        return message
    content = message_content(message)
    if not isinstance(content, str):
        return message
    delegated_view = model_visible_delegated_receipt(content)
    if delegated_view is not None:
        visible_content = json.dumps(delegated_view, ensure_ascii=False, separators=(",", ":"))
        if isinstance(message, dict):
            copied = dict(message)
            copied["content"] = visible_content
            return copied
        model_copy = getattr(message, "model_copy", None)
        if callable(model_copy):
            return model_copy(update={"content": visible_content})
        return message
    response = _as_dict(content)
    # 只处理统一 ToolResponse 信封。普通工具文本不做 JSON 改写，避免改变第三方
    # 工具协议；所有本项目 ToolResponse 不论是否生成 UI 卡片，都必须隐藏来源 ID。
    if response.get("ok") not in {True, False}:
        return message
    visible_response = _model_visible_tool_data(dict(response))
    visible_response.pop("presentation", None)
    visible_content = json.dumps(visible_response, ensure_ascii=False, separators=(",", ":"))
    if isinstance(message, dict):
        copied = dict(message)
        copied["content"] = visible_content
        return copied
    model_copy = getattr(message, "model_copy", None)
    if callable(model_copy):
        return model_copy(update={"content": visible_content})
    # 未知消息实现不强行改写，避免破坏供应商的 ToolMessage 协议。
    return message


def model_visible_messages(messages: list[Any], *, window: int = _RECENT_MESSAGE_WINDOW) -> list[Any]:
    """返回可交给模型的近窗口，并排除 UI 专用展示标识。"""

    return [_model_visible_message(message) for message in recent_model_messages(messages, window=window)]


def _candidate_priority(candidate: ContextCandidate) -> int:
    """先做业务语义的确定性优先级，再在同类候选内比较新鲜度。

    复杂距离公式属于离线评测阶段；线上第一版只采用稳定、可解释的层级排序，
    避免未经数据验证的权重让较早的查询意外压过待补计划或待确认操作。
    """

    return {
        "pending_plan": 300,
        "pending_approval": 200,
        "authorized_resource": 100,
        "authorized_query": 100,
    }[candidate.kind]


def _trusted_source_identity(candidate: ContextCandidate) -> tuple[str, str, str, str | int] | None:
    """返回候选对应的可信业务对象键，用于合并重复查询结果。

    候选的 ``candidate_id`` 是每次投影新签发的临时引用，不能用它判断两个候选
    是否指向同一业务对象。只有 ``trusted_plan`` 中已声明为授权来源字段、且为
    正整数的 ``source_*_id`` 才可参与去重；模型可见摘要、标题和 UI 的
    ``sourceResultId`` 都不能参与这个判断。
    """

    # 项目候选来自当前用户的 Java ``project.list`` 查询。这里只把 project_id
    # 当作去重键，绝不把它解释成写操作来源字段；执行项目动作时仍会重新校验。
    if candidate.capability_id == "project":
        project_id = str(candidate.trusted_plan.get("project_id") or "").strip()
        if project_id:
            return candidate.kind, candidate.capability_id, "project_id", project_id

    authorized_fields = candidate.trusted_plan.get("_authorized_source_fields")
    if not isinstance(authorized_fields, (list, tuple, set)):
        return None
    for field in authorized_fields:
        source_field = str(field or "").strip()
        if not source_field.startswith("source_") or not source_field.endswith("_id"):
            continue
        value = candidate.trusted_plan.get(source_field)
        # bool 是 int 的子类；把它当业务 ID 会把异常 checkpoint 放大成写定位器。
        if isinstance(value, bool):
            continue
        try:
            source_id = int(str(value).strip())
        except (TypeError, ValueError):
            continue
        if source_id > 0:
            return candidate.kind, candidate.capability_id, source_field, source_id
    return None


def _deduplicate_context_candidates(candidates: list[ContextCandidate]) -> list[ContextCandidate]:
    """按候选类型、领域和可信来源 ID 合并重复对象，保留较新的投影。

    调用方会把本次刚解析的消息按“从新到旧”放在旧 checkpoint 候选之前。因此
    首次遇到同一可信对象的候选就是较新的查询结果；保留它能避免反复查询同一
    日程后，模型面对多个实际上相同的候选而被错误判为歧义。
    """

    deduplicated: list[ContextCandidate] = []
    seen: set[tuple[str, str, str, int]] = set()
    for candidate in candidates:
        identity = _trusted_source_identity(candidate)
        if identity is not None:
            if identity in seen:
                continue
            seen.add(identity)
        deduplicated.append(candidate)
    return deduplicated


def _candidate_subject(candidate: ContextCandidate) -> str:
    """提取可向用户展示的对象标题，用于确定性字面引用，不做语义猜测。"""

    subject = re.sub(r"^(?:可编辑(?:会议预约|个人日程)|待确认操作|待补充的[^：]+计划)：", "", candidate.summary)
    return subject.split("，", 1)[0].split("（", 1)[0].strip()


def context_candidate_score(
    candidate: ContextCandidate,
    *,
    current_turn: int,
    user_message: str = "",
    alpha: float = 0.72,
) -> float:
    """计算硬过滤后候选的可解释排序分数。

    公式在 ``evals/evaluate_context_ranking.py`` 的固定中文样例上比较后选定：

    ``0.30 * 类型优先级 + 0.50 * 明确标题引用 + 0.20 * 0.72^回合距离``

    只有标题完整出现才给予“明确引用”分，不使用分词、embedding 或大模型语义分；
    不明确时该项为零，系统仍会在工具边界要求唯一候选或向用户澄清。
    """

    priority = _candidate_priority(candidate) / 300.0
    subject = _candidate_subject(candidate)
    explicit_reference = 1.0 if len(subject) >= 2 and subject in str(user_message or "") else 0.0
    distance = max(0, current_turn - candidate.source_turn)
    return (0.30 * priority) + (0.50 * explicit_reference) + (0.20 * (alpha ** distance))


def ordered_context_candidates(
    value: Any,
    *,
    current_turn: int | None = None,
    user_message: str = "",
) -> list[ContextCandidate]:
    """返回硬过滤后的候选顺序，供提示词和投影层使用。

    过期、跨身份、跨 Thread 的候选已在 ``_as_candidates`` 过滤。剩下的候选按
    类型优先级、回合距离、签发时间排序；此函数不根据模型文字猜测业务对象。
    """

    candidates = _as_candidates(value)
    turn = current_turn if current_turn is not None else 0
    return sorted(
        candidates,
        key=lambda candidate: (
            -context_candidate_score(candidate, current_turn=turn, user_message=user_message),
            max(0, turn - candidate.source_turn),
            -candidate.issued_at.timestamp(),
            candidate.candidate_id,
        ),
    )


_EXPLICIT_NEW_REQUEST = re.compile(
    r"^(?:请|帮我|我要|我想|查询|查看|查一下|预约|创建|新建|安排|发起|取消|修改|改成)",
)
_CONTEXT_REFERENCE = re.compile(
    r"(?:那个|这[个项]|刚才|上[一]?个|前面|上述|第[一二三四五六七八九十0-9]+个|第\s*[0-9]+\s*项|继续|补充|改成|改到|取消它|撤回|好的|好呀|行|可以|没问题|同意|确认|批准)",
)
_PROJECT_CONTEXT_REFERENCE = re.compile(
    r"(?:这个|这项|该|上述|前面(?:的)?|刚才(?:的)?|上一个|当前|本)(?:项目|工程|课题)",
)


def context_trigger_reason(messages: list[Any], candidates: Any) -> str | None:
    """判断本轮是否值得把候选注入模型，不让旧候选污染明确的新请求。"""

    user_message = ""
    for item in reversed(messages):
        if message_type(item) in {"human", "user"}:
            content = message_content(item)
            if isinstance(content, str):
                user_message = content.strip()
            break
    if not user_message:
        return None
    active = ordered_context_candidates(candidates, current_turn=_human_turn_count(messages))
    if not active:
        return None
    if _EXPLICIT_NEW_REQUEST.search(user_message) and not _CONTEXT_REFERENCE.search(user_message):
        return None
    if any(item.kind == "pending_plan" for item in active):
        return "存在待补字段计划"
    if any(item.kind == "pending_approval" for item in active) and (
        len(user_message) <= 24 or _CONTEXT_REFERENCE.search(user_message)
    ):
        return "存在待确认操作"
    if _CONTEXT_REFERENCE.search(user_message):
        return "检测到指代或续接表达"
    if len(user_message) <= 12:
        return "短消息可能省略上下文"
    return None


def _audit_update(state: dict[str, Any], *, event: str, **details: Any) -> dict[str, Any]:
    """生成轻量 checkpoint 审计记录，同时输出结构化日志供 shadow mode 观察。"""

    entry = {
        "at": datetime.now(UTC).isoformat(),
        "event": event,
        **details,
    }
    _LOG.info("conversation_context=%s", json.dumps(entry, ensure_ascii=False, default=str))
    history = list((state or {}).get("context_audit") or [])
    return {"context_audit": [*history[-39:], entry]}


def audit_context_decision(state: dict[str, Any], *, event: str, **details: Any) -> None:
    """记录工具边界的候选采用/拒绝决定，不改变不可变的模型调用 state。"""

    _audit_update(state, event=event, shadow=context_shadow_mode(), **details)


def context_candidates_state_update(state: dict[str, Any]) -> dict[str, Any] | None:
    """从可信 checkpoint 消息写入候选投影，保留尚未过期的旧候选。

    这里故意不在每个新用户回合重新请求 Java。查询结果先作为短期候选存在；
    真正进入 UPDATE/CANCEL 工作流时，业务工具仍会实时读取 Java 进行严格校验。
    """

    messages = list((state or {}).get("messages") or [])
    current_turn = _human_turn_count(messages)
    raw_existing = (state or {}).get("context_candidates")
    existing = _as_candidates(raw_existing)
    # 确认卡完成提交后不能继续和刚创建的日程竞争“那个”的指代。只按确认工具
    # 调用参数中的 approvalId 精确移除对应卡片，其他尚待确认草稿仍然保留。
    settled_approval_ids = _settled_personal_schedule_approval_ids(messages)
    if settled_approval_ids:
        existing = [
            candidate for candidate in existing
            if not (
                candidate.kind == "pending_approval"
                and str(candidate.trusted_plan.get("approval_id") or "") in settled_approval_ids
            )
        ]
    # PendingPlan 是“当前唯一待补计划”，不是可长期回看的对话记忆。编译器清空
    # 或替换它后，同步移除旧候选，避免短句被错误续接到已经结束的计划。
    if not isinstance((state or {}).get("pending_plan"), dict):
        existing = [candidate for candidate in existing if candidate.kind != "pending_plan"]
    else:
        current_plan_id = str((state or {}).get("pending_plan", {}).get("planId") or "").strip()
        existing = [
            candidate
            for candidate in existing
            if candidate.kind != "pending_plan" or candidate.trusted_plan.get("planId") == current_plan_id
        ]
    # 新版本上线前的 checkpoint 可能已经保存了重复对象。先压缩旧状态，确保它
    # 也会在下一次模型调用时收敛，而不是必须再执行一次同样的查询才生效。
    existing = _deduplicate_context_candidates(existing)
    known_source_keys = {candidate.source_tool_call_id for candidate in existing if candidate.source_tool_call_id}
    additions: list[ContextCandidate] = []
    # 倒序只扫描自上次已投影 ToolMessage 之后的新输出。checkpoint 变长后不必
    # 每个模型回合都重新解析整段历史；遇到已知调用即停止，旧候选已在 state 中。
    for message_index in range(len(messages) - 1, -1, -1):
        message = messages[message_index]
        source_key = _candidate_source_key(message, messages=messages, message_index=message_index)
        if source_key and source_key in known_source_keys:
            break
        additions.extend(_meeting_candidates(
            message, source_turn=current_turn, messages=messages, message_index=message_index,
        ))
        single_meeting = _single_meeting_candidate(
            message, source_turn=current_turn, messages=messages, message_index=message_index,
        )
        if single_meeting is not None:
            additions.append(single_meeting)
        additions.extend(_schedule_candidates(
            message, source_turn=current_turn, messages=messages, message_index=message_index,
        ))
        additions.extend(_project_candidates(
            message, source_turn=current_turn, messages=messages, message_index=message_index,
        ))
        confirmed_schedule = _confirmed_personal_schedule_candidate(
            message, source_turn=current_turn, messages=messages, message_index=message_index,
        )
        if confirmed_schedule is not None:
            additions.append(confirmed_schedule)
        party_file = _party_file_candidate(message, source_turn=current_turn)
        if party_file is not None:
            additions.append(party_file)
        approval = _approval_candidate(message, source_turn=current_turn)
        if (
            approval is not None
            and str(approval.trusted_plan.get("approval_id") or "") not in settled_approval_ids
        ):
            additions.append(approval)

    pending = _pending_candidate((state or {}).get("pending_plan"), source_turn=current_turn)
    if pending is not None and not any(
        candidate.kind == "pending_plan" and candidate.trusted_plan.get("planId") == pending.trusted_plan.get("planId")
        for candidate in existing
    ):
        additions.append(pending)

    if not additions and len(existing) == len(raw_existing or []):
        return None
    # additions 按消息倒序构建，必须在旧候选前去重，才能让同一对象最新的 Java
    # 查询替换较早快照，而不是把两个不同 candidateId 一并交给模型。
    unique_candidates = _deduplicate_context_candidates([*additions, *existing])
    # 合并后统一排序；查询候选最多保留八条，待补计划和待确认事项不会被查询列表挤掉。
    merged = ordered_context_candidates(
        [candidate.model_dump(by_alias=True, mode="json") for candidate in unique_candidates],
        current_turn=current_turn,
    )[:_MAX_CANDIDATES]
    update: dict[str, Any] = {
        "context_candidates": [candidate.model_dump(by_alias=True, mode="json") for candidate in merged],
    }
    audit = _audit_update(
        state,
        event="candidates_refreshed",
        candidateCount=len(merged),
        addedKinds=[candidate.kind for candidate in additions],
    )
    # 生产默认走结构化日志，避免每轮诊断都放大 LangGraph checkpoint。排障或
    # shadow 对照实验时设置该开关，才把最近诊断同时持久化到当前 Thread。
    if os.getenv("OA_AGENT_CONTEXT_AUDIT_CHECKPOINT", "false").strip().lower() in {"1", "true", "yes", "on"}:
        update.update(audit)
    return update


def context_candidate_for_route_call(state: dict[str, Any], candidate_id: str | None) -> ContextCandidate | None:
    """验证模型引用的候选 ID，返回服务端保存的可信定位线索。"""

    requested = str(candidate_id or "").strip()
    if not requested:
        return None
    for candidate in _as_candidates((state or {}).get("context_candidates")):
        if secrets.compare_digest(candidate.candidate_id, requested):
            return candidate
    return None


_ORDINAL_WORDS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def context_candidate_reference_is_unambiguous(
    state: dict[str, Any],
    candidate: ContextCandidate,
    *,
    user_message: str,
) -> bool:
    """判断用户是否足以唯一指定候选，禁止模型在多个对象中“挑最像的”。"""

    messages = list((state or {}).get("messages") or [])
    ordered = ordered_context_candidates(
        (state or {}).get("context_candidates"), current_turn=_human_turn_count(messages),
    )
    # 只有当前所有有效候选恰好一个时，“那个”才可自然续接。不能因为同类型
    # 候选只有一个，就忽略同时存在的待确认审批或待补计划而偷偷选中写对象。
    if len(ordered) == 1:
        return True
    text = str(user_message or "").strip()
    # “这个项目”已经把对象类型限定为项目。它与“那个”不同，不会把日程、
    # 待确认卡或待补计划混入歧义集合；因此只要当前有效项目候选唯一，就可以
    # 将其作为下一次 Java Provider 重新核验的定位线索。该例外只用于只读项目
    # 定位，不授予任何写操作来源字段。
    if candidate.capability_id == "project" and _PROJECT_CONTEXT_REFERENCE.search(text):
        project_candidates = [
            item for item in ordered
            if item.capability_id == "project"
            and item.kind in {"authorized_query", "authorized_resource"}
        ]
        if len(project_candidates) == 1 and project_candidates[0].candidate_id == candidate.candidate_id:
            return True
    ordinal = re.search(r"第\s*([0-9一二三四五六七八九十]+)\s*(?:个|项|条|场)?", text)
    if ordinal:
        raw = ordinal.group(1)
        position = int(raw) if raw.isdigit() else _ORDINAL_WORDS.get(raw, 0)
        return 1 <= position <= len(ordered) and ordered[position - 1].candidate_id == candidate.candidate_id
    # 标题/主题是用户明确说出的对象引用。去掉模板词后只采纳足够长的片段，
    # 不会用“会议”“日程”等宽泛领域词把多个对象误判为唯一对象。
    subject = _candidate_subject(candidate)
    return len(subject) >= 2 and subject in text


def context_candidate_is_recent_for_direct_lookup(state: dict[str, Any], candidate: ContextCandidate) -> bool:
    """判断候选是否仍可用内部 ID 发起定向 Java 核验。

    这不是写操作授权或事实新鲜度判断。它只控制一次性能优化：近两回合内由 Java
    查询/确认产生的候选，可以用内部 ID 精确读取；更早的候选必须走标题、时间等
    受限范围查询或向用户澄清。
    """

    messages = list((state or {}).get("messages") or [])
    return _human_turn_count(messages) - candidate.source_turn <= _DIRECT_LOOKUP_MAX_TURN_DISTANCE


def context_candidate_proof(candidate_id: str) -> str:
    """为候选 ID 生成仅投影层可写入的完整性证明。"""

    return hmac.new(_PROOF_SECRET, candidate_id.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_context_candidate_proof(candidate_id: str | None, proof: Any) -> bool:
    """验证路由调用携带的内部候选证明，拒绝模型伪造同名字段。"""

    value = str(candidate_id or "").strip()
    supplied = str(proof or "").strip()
    return bool(value and supplied) and hmac.compare_digest(
        context_candidate_proof(value), supplied,
    )


def context_prompt(value: Any, *, messages: list[Any] | None = None) -> str:
    """渲染给规划模型的中立候选摘要，避免候选污染新请求判断。"""

    message_list = list(messages or [])
    user_message = ""
    for item in reversed(message_list):
        if message_type(item) in {"human", "user"}:
            content = message_content(item)
            user_message = content.strip() if isinstance(content, str) else ""
            break
    candidates = ordered_context_candidates(
        value,
        current_turn=_human_turn_count(message_list),
        user_message=user_message,
    )
    if not candidates:
        return ""
    trigger = context_trigger_reason(message_list, value) if message_list else "候选存在"
    if not trigger:
        return ""
    lines = [
        f"当前消息触发上下文判断（原因：{trigger}）。以下候选仅供理解，不代表必须续接：",
    ]
    current_turn = _human_turn_count(message_list)
    for index, candidate in enumerate(candidates, start=1):
        distance = max(0, current_turn - candidate.source_turn)
        lines.append(
            f"- 候选 {index}（ID={candidate.candidate_id}；状态={candidate.status}；距当前 {distance} 回合）：{candidate.summary}"
        )
    lines.extend(
        [
            "先判断 context_intent：新请求用 NEW_REQUEST；补充待补计划用 RESUME_PENDING_PLAN；",
            "修改/取消已授权对象用 REFER_TO_QUERY_CANDIDATE；回应待确认操作用 LOCATE_APPROVAL_CARD；",
            "多个候选而用户没有明确名称或序号时用 AMBIGUOUS，不能猜测对象。",
            "同时填写 0 到 1 的 context_confidence；引用查询对象低于 0.70 时必须澄清，不能绑定写操作来源。",
            "用户明确指向唯一项目候选（如“就这个项目”“这个项目”或项目名称）并请求项目概览、进度、任务、",
            "风险、资料、检索或报告时，也应传 context_candidate_id，并用 REFER_TO_QUERY_CANDIDATE；",
            "这只解决“指的是哪个项目”，后续仍会重新查询 Java Project Provider，不能把候选当作项目事实。",
            "只有确实在引用上述查询对象时才传 context_candidate_id。不得自行填写 source ID、",
            "_authorized_source_fields 或任何授权标记；界面结果标识 sourceResultId/result:... 不是候选 ID。",
            "待确认操作只能定位正式确认卡，不能替代审批确认。",
        ]
    )
    return "\n".join(lines)


class ContextCandidateMiddleware(AgentMiddleware):
    """在模型调用前更新 checkpoint 中的受限上下文候选。"""

    name = "ContextCandidateMiddleware"
    state_schema = ContextCandidateState

    def before_model(self, state, runtime):
        return context_candidates_state_update(state)

    async def abefore_model(self, state, runtime):
        return context_candidates_state_update(state)

    def wrap_model_call(self, request, handler):
        """在不改变 checkpoint 的前提下，把有限近窗口交给模型。"""

        return handler(request.override(messages=model_visible_messages(list(request.messages or []))))

    async def awrap_model_call(self, request, handler):
        """异步模型调用使用与同步路径完全一致的窗口规则。"""

        return await handler(request.override(messages=model_visible_messages(list(request.messages or []))))


__all__ = [
    "ContextCandidate",
    "ContextCandidateMiddleware",
    "ContextCandidateState",
    "ContextIntent",
    "context_candidate_for_route_call",
    "context_candidate_is_recent_for_direct_lookup",
    "context_candidate_score",
    "context_shadow_mode",
    "context_candidate_proof",
    "context_candidates_state_update",
    "context_trigger_reason",
    "model_visible_messages",
    "audit_context_decision",
    "context_prompt",
    "ordered_context_candidates",
    "recent_model_messages",
    "verify_context_candidate_proof",
]
