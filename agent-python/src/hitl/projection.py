"""One implementation of the draft-to-ApprovalCard projection pattern."""

from __future__ import annotations

from copy import copy
from dataclasses import replace
from hashlib import sha256
from typing import Any, Callable

from langchain_core.messages import AIMessage

from ..middleware.approval_projection import is_draft_projection_turn
from ..services.approval_core import PROJECTION_METADATA_KEY, approval_projection_metadata


def _replace_response(response: Any, messages: list[Any]) -> Any:
    try:
        return replace(response, result=messages)
    except TypeError:
        value = copy(response)
        value.result = messages
        return value


def project_confirmation_call(
    request: Any,
    response: Any,
    *,
    source_tools: set[str] | frozenset[str],
    delegated_eligible: bool = False,
    context_loader: Callable[[], tuple[Any | None, Any | None]],
    action_name: Callable[[Any], str] | str,
    args_builder: Callable[[Any, dict[str, Any]], dict[str, Any]],
    identity_builder: Callable[[Any], tuple[str, ...]],
    projection_builder: Callable[[Any, str], dict[str, str]],
    call_id_prefix: str,
) -> Any:
    """Replace the model's final call with exactly one trusted confirmation.

    The domain-specific services still own loading and validating their
    durable draft. This helper owns only the presentation mutation, so a new
    approval type cannot accidentally invent a sixth copy of the injection
    algorithm.
    """
    # 委托场景的资格必须由领域中间件先验证强类型回执，再显式传入。这里不再
    # 根据“任务发给了哪个子 Agent”判断，避免普通执行回执也能误生成确认卡。
    if not (is_draft_projection_turn(request, source_tools) or delegated_eligible):
        return response
    context, error = context_loader()
    messages = getattr(response, "result", None)
    if error is not None or context is None or not messages:
        return response
    index = next((i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], AIMessage)), None)
    if index is None:
        return response
    name = action_name(context) if callable(action_name) else action_name
    identity = "\x1f".join(str(item or "") for item in identity_builder(context))
    call = {
        "name": name,
        "args": args_builder(context, {}),
        "id": f"{call_id_prefix}-{sha256(identity.encode('utf-8')).hexdigest()[:24]}",
        "type": "tool_call",
    }
    projection = projection_builder(context, name)
    target = messages[index].model_copy(deep=True, update={
        "tool_calls": [call],
        "additional_kwargs": {
            **(messages[index].additional_kwargs or {}),
            PROJECTION_METADATA_KEY: projection,
        },
    })
    updated = list(messages)
    updated[index] = target
    return _replace_response(response, updated)


__all__ = ["project_confirmation_call"]
