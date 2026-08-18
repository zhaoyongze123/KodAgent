"""Pure helpers shared by domain plan compilers."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def plan_id(capability_id: str, execution_class: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"capability": capability_id, "class": execution_class, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


def present(value: Any) -> bool:
    return value not in (None, "", [], {})


def int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def copy_registered_fields(payload: dict[str, Any], action: Any) -> dict[str, Any]:
    """Copy only fields owned by the registered Java action contract."""
    values: dict[str, Any] = {}
    # ActionSpec exposes its fields through the public helper rather than a
    # ``field_specs`` attribute.  Keep this utility provider-neutral and make
    # the catalog the single source of truth for accepted fields.
    from ..capabilities import action_field_specs

    for field in action_field_specs(action) if action is not None else ():
        if present(payload.get(field.name)):
            values[field.name] = payload[field.name]
    return values


__all__ = ["copy_registered_fields", "int_or_none", "plan_id", "present"]
