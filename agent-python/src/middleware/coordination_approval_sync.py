"""确认卡完成后同步跨领域协作批次状态。

文件职责
========
跨领域批次中的写步骤在草稿生成时停在 ``WAITING_APPROVAL``。正式确认仍完全复用
会议、日程、审批和党务原有的 HITL 工具；本中间件不生成确认卡、不改变确认参数，
只在确认工具已经返回后读取该 Operation 的终态，并更新引用它的协作步骤。

这样“批次编排状态”与“领域业务写入状态”既能关联，也不会把批次层变成第二个
提交入口。
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware

from ..orchestration.coordination_dispatch import sync_operation_completion
from ..tools.common.events import current_agent_context


_CONFIRMATION_TOOLS = frozenset({
    "confirm_meeting_booking",
    "confirm_personal_schedule",
    "confirm_approval_request_action",
    "confirm_approval_withdraw_action",
    "confirm_approval_batch_action",
    "confirm_approval_task_action",
    "confirm_create_party_file",
    "confirm_update_party_file",
    "confirm_delete_party_file",
})


class CoordinationApprovalSyncMiddleware(AgentMiddleware):
    """将已确认/拒绝的 Operation 终态回写到对应协作批次。"""

    name = "CoordinationApprovalSyncMiddleware"

    @staticmethod
    def _confirmation_call(request: Any) -> bool:
        call = getattr(request, "tool_call", None) or {}
        return str(call.get("name") or "") in _CONFIRMATION_TOOLS

    @staticmethod
    def _sync() -> None:
        # 领域确认服务在校验草稿、审批卡和运行身份后会绑定 operationId。这里
        # 只使用这个已受信任的运行上下文，绝不从模型的确认参数猜 Operation。
        operation_id = str(current_agent_context().get("operationId") or "").strip()
        if operation_id:
            sync_operation_completion(operation_id)

    def wrap_tool_call(self, request, handler):
        if not self._confirmation_call(request):
            return handler(request)
        result = handler(request)
        self._sync()
        return result

    async def awrap_tool_call(self, request, handler):
        if not self._confirmation_call(request):
            return await handler(request)
        result = await handler(request)
        self._sync()
        return result


__all__ = ["CoordinationApprovalSyncMiddleware"]
