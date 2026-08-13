"""在会议子 Agent 与主 Agent 的边界发布已核验的工作流结果回执。"""

from __future__ import annotations

from typing import NotRequired

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import ToolMessage

from ..orchestration.delegated_receipt import meeting_workflow_receipt_from_workflow_message
from ..orchestration.domain_dispatch import parse_work_order


class MeetingExecutionReceiptState(AgentState):
    """DeepAgents 子 Agent 向父图传递结构化结果所需的状态扩展。"""

    structured_response: NotRequired[dict[str, object]]


class MeetingExecutionReceiptMiddleware(AgentMiddleware):
    """把一次会议工作流 ToolMessage 转成主图可验证的回执。

    ``after_agent`` 在子 Agent 完成工具调用后、DeepAgents 将子图收敛为父图
    ``task`` ToolMessage 前运行。返回 ``structured_response`` 可避免框架退回
    到会丢失业务数据的“最后一段助手文本”传输方式。
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

    @staticmethod
    def _work_order(state):
        for message in reversed((state or {}).get("messages") or []):
            content = message.get("content", "") if isinstance(message, dict) else getattr(message, "content", "")
            work_order = parse_work_order(str(content or ""))
            if work_order is not None:
                return work_order
        return None

    def after_agent(self, state, runtime):
        workflow_messages = self._workflow_messages(state)
        # A receipt represents exactly one bounded workflow execution.  Do
        # not choose among multiple outputs, since doing so would recreate a
        # history-scanning ambiguity at the transport boundary.
        if len(workflow_messages) != 1:
            return None
        work_order = self._work_order(state)
        if work_order is None or work_order.execution_tool != "run_meeting_booking_workflow":
            return None
        receipt = meeting_workflow_receipt_from_workflow_message(
            workflow_messages[0],
            plan_id=work_order.plan_id,
        )
        if receipt is None:
            return None
        return {"structured_response": receipt.model_dump(by_alias=True, exclude_none=True)}

    async def aafter_agent(self, state, runtime):
        return self.after_agent(state, runtime)


__all__ = ["MeetingExecutionReceiptMiddleware", "MeetingExecutionReceiptState"]
