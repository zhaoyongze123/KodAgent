"""主 Agent 消息的展示契约。

LangGraph checkpoint 需要保留路由、工具调用和 HITL 的协议消息，但浏览器聊天
正文只能消费已经提交的最终回答。本模块只定义这一展示边界；不参与路由、业务
校验或卡片内容的生成。
"""

from __future__ import annotations

from typing import Any, Literal


PRESENTATION_KEY = "kodagentPresentation"
PresentationKind = Literal["internal", "final"]


def _presentation(message: Any) -> dict[str, Any] | None:
    """Return a valid current-version presentation record only.

    A checkpoint is durable input to both the browser and lifecycle audit.
    Treating a malformed or legacy record as a new final answer would make an
    old routing message visible again after a deployment, so v2 is deliberately
    fail-closed here. Historical transcript compatibility belongs to the UI
    projection, not the runtime's completion audit.
    """

    additional = (
        message.get("additional_kwargs")
        if isinstance(message, dict)
        else getattr(message, "additional_kwargs", None)
    )
    if not isinstance(additional, dict):
        return None
    presentation = additional.get(PRESENTATION_KEY)
    if not isinstance(presentation, dict):
        return None
    return presentation if presentation.get("schemaVersion") == 2 else None


def presentation_kind(message: Any) -> str | None:
    """返回当前 v2 的展示类别；旧或损坏 checkpoint 不认定为 final。"""

    presentation = _presentation(message)
    if presentation is None:
        return None
    kind = str(presentation.get("kind") or "").strip().lower()
    if kind == "internal":
        return kind
    if kind == "final" and presentation_final_entry_id(message):
        return kind
    return None


def presentation_final_entry_id(message: Any) -> str | None:
    """读取最终回答流和 checkpoint 消息的共享关联标识。"""

    presentation = _presentation(message)
    if presentation is None or str(presentation.get("kind") or "").strip().lower() != "final":
        return None
    entry_id = presentation.get("finalEntryId")
    return str(entry_id).strip() or None if entry_id is not None else None


def with_message_presentation(
    message: Any,
    *,
    kind: PresentationKind,
    final_entry_id: str | None = None,
) -> Any:
    """返回带展示契约的新消息，并保留既有卡片投影字段。"""

    if not hasattr(message, "model_copy"):
        return message
    resolved_entry_id = str(final_entry_id or "").strip()
    if kind == "final" and not resolved_entry_id:
        raise ValueError("final presentation requires final_entry_id")
    current_kwargs = dict(getattr(message, "additional_kwargs", None) or {})
    presentation = dict(current_kwargs.get(PRESENTATION_KEY) or {})
    presentation.update({"schemaVersion": 2, "kind": kind})
    presentation.pop("version", None)
    if resolved_entry_id:
        presentation["finalEntryId"] = resolved_entry_id
    elif kind == "internal":
        presentation.pop("finalEntryId", None)
    current_kwargs[PRESENTATION_KEY] = presentation
    return message.model_copy(
        deep=True,
        update={"additional_kwargs": current_kwargs},
    )


__all__ = [
    "PRESENTATION_KEY",
    "PresentationKind",
    "presentation_final_entry_id",
    "presentation_kind",
    "with_message_presentation",
]
