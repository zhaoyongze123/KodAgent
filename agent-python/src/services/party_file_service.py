"""Business rules shared by party-file tools and workflows.

The tool layer owns LangChain argument binding and presentation only.  This
module contains the deterministic category and target normalization rules so
the same semantics are used by create, update, import and future attachment
flows without depending on a tool module's globals.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Any


_CANONICAL_CATEGORIES = frozenset({"组织建设", "会议活动", "制度规范", "通知公告", "上级文件"})


def infer_category_name(title: str, document_type: str = "") -> str:
    """Infer only a human-facing category name from document text.

    No internal ID is invented here; the tenant's enabled category list is
    still the authority used by :func:`resolve_category_id`.
    """
    text = f"{document_type} {title}".strip()
    if re.search(r"通知|通报|公告|公示", text):
        return "通知公告"
    if re.search(r"制度|规定|办法|规范|条例|细则", text):
        return "制度规范"
    if re.search(r"会议|活动|培训|演练", text):
        return "会议活动"
    if re.search(r"组织|党支部|党员|党建", text):
        return "组织建设"
    if re.search(r"上级|中央|省委|市委|国务院", text):
        return "上级文件"
    return ""


def canonical_category_name(category_name: str, title: str = "", document_type: str = "") -> str:
    """Normalize common natural-language aliases without changing custom OA names."""
    raw = str(category_name or "").strip()
    if not raw:
        return infer_category_name(title, document_type)
    if raw in _CANONICAL_CATEGORIES:
        return raw
    return infer_category_name(raw) or raw


def resolve_category_id(
    category_id: int | None,
    category_name: str | None,
    *,
    category_loader: Callable[[str], Sequence[dict[str, Any]]] | None = None,
) -> int | None:
    """Resolve an OA category name using the injected tenant read adapter."""
    if category_id is not None:
        return int(category_id)
    name = str(category_name or "").strip()
    if not name:
        return None
    if category_loader is None:
        raise ValueError("党务文件分类查询未配置")
    try:
        categories = category_loader("/agent/tools/party-files/categories")
    except Exception as exc:
        raise ValueError(f"党务文件分类查询失败: {exc}") from exc
    matches = [
        item for item in (categories if isinstance(categories, Sequence) else [])
        if isinstance(item, dict) and str(item.get("name") or "").strip() == name
    ]
    if len(matches) == 1:
        try:
            return int(matches[0]["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"党务文件分类“{name}”缺少有效 ID") from exc
    if not matches:
        raise ValueError(f"未找到启用的党务文件分类“{name}”")
    raise ValueError(f"党务文件分类“{name}”不唯一")


def normalize_targets(
    targets: list[dict[str, Any]] | None,
    distribute_to_self: bool,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Normalize the explicit or authenticated-user distribution target."""
    if targets:
        return targets
    if not distribute_to_self:
        return []
    try:
        user_id = int(str(context.get("userId") or ""))
    except (TypeError, ValueError) as exc:
        raise ValueError("当前身份缺少有效 userId，无法设置本人为分发对象") from exc
    return [{"targetType": 2, "targetId": user_id}]


__all__ = [
    "canonical_category_name",
    "infer_category_name",
    "normalize_targets",
    "resolve_category_id",
]
