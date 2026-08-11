import os
from typing import NotRequired

from langchain.agents.middleware import AgentMiddleware, AgentState, ToolCallLimitMiddleware

from ..tools.common import current_agent_context
from ..tools.common.events import set_message_context, turn_id_from_context
from .pending_plan import pending_plan_state_update


def _message_text(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(message, dict):
        content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content).strip()
    return str(content or "").strip()


class CurrentUserMessageState(AgentState):
    current_user_message: NotRequired[dict[str, object] | None]


class PendingPlanState(AgentState):
    pending_plan: NotRequired[dict[str, object] | None]


class CurrentUserMessageMiddleware(AgentMiddleware):
    """Propagate only a trusted real HumanMessage across a sub-agent boundary."""

    name = "CurrentUserMessageMiddleware"
    state_schema = CurrentUserMessageState

    def __init__(self, *, trusted_source: bool):
        super().__init__()
        self.trusted_source = trusted_source

    def _update(self, state):
        context = current_agent_context()
        existing = state.get("current_user_message") if isinstance(state, dict) else None

        # A LangGraph HITL resume is a new transport Run, but it is still the
        # original business action.  The resume metadata carries the durable
        # approval-bound messageId; walking the checkpoint's HumanMessage here
        # would replace it with the original chat message id and make Java's
        # exact draft/approval binding fail.  Keep the trusted resume envelope
        # authoritative while allowing the model to replay the saved state.
        if str(context.get("resumeRunId") or "").strip():
            return None

        if not self.trusted_source:
            return {"current_user_message": None}
        # A normal user submission appends a HumanMessage to the checkpoint.
        # Always bind that latest message *before* considering a checkpointed
        # marker.  The old order restored the previous marker whenever the
        # transport omitted messageId, which let a new request inherit the
        # old meeting Operation and pending plan.
        for message in reversed((state or {}).get("messages") or []):
            role = getattr(message, "type", None)
            if isinstance(message, dict):
                role = message.get("type") or message.get("role")
            if str(role or "").lower() not in {"human", "user"}:
                continue
            text = _message_text(message)
            if not text:
                return None
            raw_id = getattr(message, "id", None)
            if isinstance(message, dict):
                raw_id = message.get("id") or message.get("message_id")
            message_id = str(raw_id or "").strip()
            if not message_id:
                previous_text = str(existing.get("text") or "") if isinstance(existing, dict) else ""
                previous_id = str(existing.get("messageId") or "").strip() if isinstance(existing, dict) else ""
                # A model/tool re-entry for the same user turn may lack a
                # message id. Preserve its existing binding only when the
                # actual latest HumanMessage is unchanged; new text must get
                # a fresh turn identity instead of reviving the old one.
                message_id = previous_id if previous_id and previous_text == text else turn_id_from_context(context)
            set_message_context(message_id)
            return {"current_user_message": {"source": "current_human_message", "messageId": message_id, "text": text, "trusted": True}}
        # Tool->model re-entry can carry a compact state delta with no
        # HumanMessage at all.  Only in that case is the checkpoint marker the
        # surviving identity source; a real new HumanMessage above always
        # wins and therefore cannot inherit this old binding.
        if isinstance(existing, dict) and existing.get("source") == "current_human_message" and existing.get("trusted") is True:
            trusted_message_id = str(existing.get("messageId") or "").strip()
            if trusted_message_id:
                set_message_context(trusted_message_id)
        return None

    def before_model(self, state, runtime):
        return self._update(state)

    async def abefore_model(self, state, runtime):
        return self._update(state)


class PendingPlanMiddleware(AgentMiddleware):
    """Persist a compiler clarification in the LangGraph thread checkpoint."""

    name = "PendingPlanMiddleware"
    state_schema = PendingPlanState

    def before_model(self, state, runtime):
        return pending_plan_state_update(state)

    async def abefore_model(self, state, runtime):
        return pending_plan_state_update(state)


MEETING_SINGLE_CALL_TOOL_NAMES = (
    "prepare_meeting_booking_request",
    "list_available_meeting_rooms",
    "check_meeting_availability_batch",
)


def meeting_tool_call_limit_middleware() -> list[ToolCallLimitMiddleware]:
    return [ToolCallLimitMiddleware(tool_name=name, run_limit=1, exit_behavior="end") for name in MEETING_SINGLE_CALL_TOOL_NAMES]


def meeting_workflow_limit_middleware() -> ToolCallLimitMiddleware:
    limit = max(8, int(os.getenv("OA_AGENT_MEETING_MAX_TOOL_CALLS", "20")))
    return ToolCallLimitMiddleware(run_limit=limit, exit_behavior="end")


def meeting_booking_workflow_once_middleware() -> ToolCallLimitMiddleware:
    """限制一次子 Agent 委托只能启动一次会议写工作流。

    工作流内部已经包含准备、会议室查询、冲突校验和草稿创建；再次调用不会
    获得新的业务能力，只会扩大重复写入和重复事件的风险。
    """
    return ToolCallLimitMiddleware(
        tool_name="run_meeting_booking_workflow", run_limit=1, exit_behavior="end",
    )


def personal_schedule_workflow_once_middleware() -> ToolCallLimitMiddleware:
    """一次委托只能启动一次个人日程写工作流。"""
    return ToolCallLimitMiddleware(
        tool_name="run_personal_schedule_workflow", run_limit=1, exit_behavior="end",
    )


def main_approval_tool_limit_middleware() -> ToolCallLimitMiddleware:
    return ToolCallLimitMiddleware(tool_name="confirm_meeting_booking", run_limit=1, exit_behavior="end")
