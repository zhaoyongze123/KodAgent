"""限制 OA Agent 的运行时工具面板和执行边界。

文件职责
========
DeepAgents 会按默认外壳注册文件系统、待办和命令工具。它们适用于通用代码助手，
但不是 OA 业务 Agent 的能力，进入模型工具列表后会造成无关调用、空结果标签和
审计事件与前端过程不一致。

本中间件同时守住两个边界：

* ``wrap_model_call``：每次模型请求前从真实 ``request.tools`` 中移除无关工具；
* ``wrap_tool_call``：旧 checkpoint 或模型伪造调用时再次拒绝执行。

因此不能只依赖 HarnessProfile，也不能把问题留给前端去隐藏。业务工具的白名单仍
由路由和 WorkOrder 中间件决定，本文件只负责全局禁止的通用工具集合。
"""

from __future__ import annotations

import json
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage


# OA Agent 不提供文件系统、shell 和通用待办能力。项目资料必须经由 Java Project
# Provider 校验权限后读取，不能让模型绕过业务工具直接访问工作目录。
FORBIDDEN_RUNTIME_TOOLS = frozenset({
    "write_todos",
    "ls",
    "read_file",
    "write_file",
    "edit_file",
    "glob",
    "grep",
    "execute",
})


def _tool_name(value: Any) -> str:
    if isinstance(value, dict):
        function = value.get("function")
        function_name = function.get("name") if isinstance(function, dict) else ""
        return str(value.get("name") or function_name or "").strip()
    return str(getattr(value, "name", "") or "").strip()


class ToolVisibilityMiddleware(AgentMiddleware):
    """在模型调用和执行调用两处阻断非业务工具。"""

    name = "ToolVisibilityMiddleware"

    @staticmethod
    def _filtered_tools(tools: Any) -> list[Any]:
        return [item for item in (tools or []) if _tool_name(item) not in FORBIDDEN_RUNTIME_TOOLS]

    def wrap_model_call(self, request, handler):
        filtered = self._filtered_tools(getattr(request, "tools", None))
        # 每次都返回副本，避免修改 DeepAgents 共享的工具列表，影响另一个 Run。
        return handler(request.override(tools=filtered))

    async def awrap_model_call(self, request, handler):
        filtered = self._filtered_tools(getattr(request, "tools", None))
        return await handler(request.override(tools=filtered))

    @staticmethod
    def _rejection(request) -> ToolMessage:
        call = getattr(request, "tool_call", None) or {}
        name = _tool_name(call) or "unknown"
        call_id = str(call.get("id") or "") if isinstance(call, dict) else ""
        return ToolMessage(
            name=name,
            tool_call_id=call_id,
            status="error",
            content=json.dumps({
                "ok": False,
                "code": "TOOL_NOT_ALLOWED",
                "message": f"工具 {name} 不属于 OA Agent 的业务能力，已拒绝执行。",
            }, ensure_ascii=False, separators=(",", ":")),
        )

    def wrap_tool_call(self, request, handler):
        if _tool_name(getattr(request, "tool_call", None)) in FORBIDDEN_RUNTIME_TOOLS:
            return self._rejection(request)
        return handler(request)

    async def awrap_tool_call(self, request, handler):
        if _tool_name(getattr(request, "tool_call", None)) in FORBIDDEN_RUNTIME_TOOLS:
            return self._rejection(request)
        return await handler(request)


__all__ = ["FORBIDDEN_RUNTIME_TOOLS", "ToolVisibilityMiddleware"]
