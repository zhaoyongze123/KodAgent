"""把普通子 Agent 的真实 executor 结果转换成根图可验证的完成回执。"""

from __future__ import annotations

from typing import NotRequired

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import ToolMessage

from ..orchestration.delegated_receipt import (
    draft_receipt_from_tool_response,
    execution_receipt_from_tool_response,
)
from ..orchestration.domain_dispatch import parse_work_order
from ..tools.common import ToolResponse


class ExecutionReceiptState(AgentState):
    """DeepAgents 使用 structured_response 把代码拥有的结果传回 task。"""

    structured_response: NotRequired[dict[str, object]]


class ExecutionReceiptMiddleware(AgentMiddleware):
    """把本次 WorkOrder 的唯一 executor 结果发布为通用结构化回执。"""

    name = "ExecutionReceiptMiddleware"

    def __init__(self, *, skip_tools: frozenset[str] = frozenset()) -> None:
        self._skip_tools = skip_tools

    @staticmethod
    def _work_order(state):
        for message in reversed((state or {}).get("messages") or []):
            content = getattr(message, "content", "")
            if isinstance(message, dict):
                content = message.get("content", "")
            work_order = parse_work_order(str(content or ""))
            if work_order is not None:
                return work_order
        return None

    def after_agent(self, state, runtime):
        work_order = self._work_order(state)
        if work_order is None or work_order.execution_tool in self._skip_tools:
            return None
        messages = [
            message for message in (state.get("messages") or [])
            if isinstance(message, ToolMessage)
            and str(message.name or "") == work_order.execution_tool
        ]
        # 一个 WorkOrder 只能产生一个 terminal executor 结果，避免从历史中
        # 猜测“哪一次才算成功”。helper 和拒绝 ToolMessage 都不会进入这里。
        if len(messages) != 1:
            return None
        try:
            result = ToolResponse.model_validate_json(str(messages[0].content or ""))
        except (TypeError, ValueError):
            return None
        # 写工作流先尝试生成领域级草稿回执。只有该回执才有资格在父图触发
        # HITL；其他成功结果仍严格使用通用执行回执。
        receipt = draft_receipt_from_tool_response(
            result,
            domain=work_order.domain,
            operation=str(work_order.canonical_plan.get("operation") or ""),
        ) or execution_receipt_from_tool_response(
            result, plan_id=work_order.plan_id, executor_tool=work_order.execution_tool,
        )
        # 省略空字段，使跨图回执只承载真实 executor 返回的业务事实；这也让
        # “字段不存在”和“字段值为 null”在主图侧保持明确区分。
        return {"structured_response": receipt.model_dump(by_alias=True, exclude_none=True)}

    async def aafter_agent(self, state, runtime):
        return self.after_agent(state, runtime)


__all__ = ["ExecutionReceiptMiddleware", "ExecutionReceiptState"]
