"""Single execution boundary for tools called by deterministic workflows.

LangChain owns the public Agent tool lifecycle.  Deterministic workflow nodes
still need to call the same tools without reaching into ``Tool.func``
directly.  This adapter applies the shared contract guard (also for standalone
workflow tests) and then uses ``Tool.invoke`` so schema validation and tool
callbacks remain part of the call boundary.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langchain_core.messages import ToolMessage

from .contracts import apply_tool_contracts


def invoke_tool(tool: Any, payload: Mapping[str, Any] | None = None, **kwargs: Any) -> Any:
    """Invoke a registered LangChain tool through the canonical boundary.

    This function is also used by deterministic StateGraph nodes.  Those
    calls must retain LangChain's full ToolCall shape: passing a plain args
    mapping cannot populate ``InjectedToolCallId`` and fails before the tool
    function is entered.
    """

    if payload is not None and kwargs:
        raise TypeError("invoke_tool accepts either payload or keyword arguments")
    values = dict(payload or kwargs)
    invoke = getattr(tool, "invoke", None)
    if not callable(invoke):
        # Workflow tests may replace a Tool with a tiny namespace exposing
        # only ``func``.  Keep that test seam compatible; real production
        # tools are StructuredTool instances and always take the branch below.
        func = getattr(tool, "func", None)
        if not callable(func):
            raise TypeError(f"对象不是可调用的 LangChain Tool: {tool!r}")
        return func(**values)
    # ``apply_tool_contracts`` is idempotent for an already guarded Tool.  It
    # also makes direct workflow/unit calls safe when no Agent was built first.
    apply_tool_contracts([tool])
    call_id = str(values.pop("tool_call_id", "") or "workflow")
    tool_call = {
        "name": str(getattr(tool, "name", "workflow_tool")),
        "args": values,
        "id": call_id,
        "type": "tool_call",
    }
    result = invoke(tool_call)
    # StateGraph nodes consume the same canonical JSON content as the legacy
    # workflow adapter, while LangChain's public ToolNode keeps ToolMessage
    # objects at the Agent boundary.
    return result.content if isinstance(result, ToolMessage) else result


__all__ = ["invoke_tool"]
