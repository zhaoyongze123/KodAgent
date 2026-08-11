"""Publish a verified meeting-workflow receipt at the child/root boundary."""

from __future__ import annotations

from typing import NotRequired

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import ToolMessage

from ..orchestration.delegated_receipt import meeting_draft_receipt_from_workflow_message


class MeetingExecutionReceiptState(AgentState):
    """State extension consumed by DeepAgents' CompiledSubAgent protocol."""

    structured_response: NotRequired[dict[str, object]]


class MeetingExecutionReceiptMiddleware(AgentMiddleware):
    """Convert one workflow ToolMessage into a code-owned task receipt.

    ``after_agent`` executes after the meeting child has finished its tools,
    before DeepAgents reduces the child state to the root ``task`` ToolMessage.
    Returning ``structured_response`` selects the framework's structured
    transport path instead of its lossy "last assistant text" fallback.
    """

    name = "MeetingExecutionReceiptMiddleware"
    state_schema = MeetingExecutionReceiptState

    @staticmethod
    def _workflow_messages(state):
        messages = state.get("messages") if isinstance(state, dict) else None
        if not isinstance(messages, list):
            return []
        return [
            message
            for message in messages
            if isinstance(message, ToolMessage)
            and str(message.name or "") == "run_meeting_booking_workflow"
        ]

    def after_agent(self, state, runtime):
        workflow_messages = self._workflow_messages(state)
        # A receipt represents exactly one bounded workflow execution.  Do
        # not choose among multiple outputs, since doing so would recreate a
        # history-scanning ambiguity at the transport boundary.
        if len(workflow_messages) != 1:
            return None
        receipt = meeting_draft_receipt_from_workflow_message(workflow_messages[0])
        if receipt is None:
            return None
        return {"structured_response": receipt.model_dump(by_alias=True)}

    async def aafter_agent(self, state, runtime):
        return self.after_agent(state, runtime)


__all__ = ["MeetingExecutionReceiptMiddleware", "MeetingExecutionReceiptState"]
