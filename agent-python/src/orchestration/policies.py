import os
from typing import NotRequired

from langchain.agents.middleware import AgentMiddleware, AgentState, ToolCallLimitMiddleware

from ..tools.common import current_agent_context
from ..tools.common.events import set_message_context, turn_id_from_context


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


class CurrentUserMessageMiddleware(AgentMiddleware):
    """Propagate only a trusted real HumanMessage across a sub-agent boundary."""

    name = "CurrentUserMessageMiddleware"
    state_schema = CurrentUserMessageState

    def __init__(self, *, trusted_source: bool):
        super().__init__()
        self.trusted_source = trusted_source

    def _update(self, state):
        context = current_agent_context()
        message_id = str(context.get("messageId") or "")
        existing = state.get("current_user_message") if isinstance(state, dict) else None

        # A LangGraph HITL resume is a new transport Run, but it is still the
        # original business action.  The resume metadata carries the durable
        # approval-bound messageId; walking the checkpoint's HumanMessage here
        # would replace it with the original chat message id and make Java's
        # exact draft/approval binding fail.  Keep the trusted resume envelope
        # authoritative while allowing the model to replay the saved state.
        if str(context.get("resumeRunId") or "").strip():
            return None

        if isinstance(existing, dict) and existing.get("source") == "current_human_message" and existing.get("trusted") is True:
            # The LangGraph model/tool re-entry can restore the checkpoint state
            # while the ContextVar envelope has been rebuilt without
            # messageId.  The checkpoint's trusted human-message binding is
            # the canonical value for this turn; restore it before any
            # approval/Java identity check runs.  Returning without restoring
            # it makes a valid draft look unrelated and suppresses HITL.
            trusted_message_id = str(existing.get("messageId") or "").strip()
            if trusted_message_id and (not message_id or trusted_message_id == message_id):
                set_message_context(trusted_message_id)
                return None
        if not self.trusted_source:
            return {"current_user_message": None}
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
            message_id = str(raw_id or "").strip() or turn_id_from_context(context)
            set_message_context(message_id)
            return {"current_user_message": {"source": "current_human_message", "messageId": message_id, "text": text, "trusted": True}}
        return None

    def before_model(self, state, runtime):
        return self._update(state)

    async def abefore_model(self, state, runtime):
        return self._update(state)


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


def main_approval_tool_limit_middleware() -> ToolCallLimitMiddleware:
    return ToolCallLimitMiddleware(tool_name="confirm_meeting_booking", run_limit=1, exit_behavior="end")
