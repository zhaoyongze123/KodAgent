"""Per-run Java-owned action catalog overlay.

The Python registry keeps the executor binding (the model must never receive
tool names or Java URLs), while Java owns the business contract: fields,
permissions, confirmation and read/write semantics.  This module stores the
validated Java snapshot for the current Run so prompts and compile-time
validation do not silently keep using stale Python field definitions.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any


_CATALOG: ContextVar[dict[str, dict[str, Any]] | None] = ContextVar(
    "kodagent_runtime_action_catalog", default=None
)
_META: ContextVar[dict[str, Any] | None] = ContextVar(
    "kodagent_runtime_action_catalog_meta", default=None
)


def set_runtime_action_catalog(
    actions: list[dict[str, Any]], *, contract_version: str | None = None,
    fingerprint: str | None = None,
) -> None:
    values = {
        str(item.get("actionId")): dict(item)
        for item in actions
        if isinstance(item, dict) and str(item.get("actionId") or "").strip()
    }
    _CATALOG.set(values)
    _META.set({"contractVersion": contract_version, "fingerprint": fingerprint})


def clear_runtime_action_catalog() -> None:
    _CATALOG.set(None)
    _META.set(None)


def runtime_action(action_id: str | None) -> dict[str, Any] | None:
    catalog = _CATALOG.get()
    if not catalog or not action_id:
        return None
    return catalog.get(str(action_id))


def runtime_action_catalog() -> dict[str, dict[str, Any]] | None:
    return _CATALOG.get()


def runtime_action_catalog_meta() -> dict[str, Any] | None:
    return _META.get()


__all__ = [
    "clear_runtime_action_catalog",
    "runtime_action",
    "runtime_action_catalog",
    "runtime_action_catalog_meta",
    "set_runtime_action_catalog",
]
