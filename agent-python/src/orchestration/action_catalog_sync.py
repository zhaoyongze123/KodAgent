"""Synchronize the Python planner with the Java-owned action contract."""

from __future__ import annotations

import hashlib
import json
import os
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from ..tools.common.contracts import get_tool_contract
from ..tools.common.http_client import get_agent_action_catalog
from .capabilities import ACTION_SPECS, action_constraints, action_field_specs, action_required_fields
from .action_catalog_runtime import clear_runtime_action_catalog, set_runtime_action_catalog


class ActionCatalogSyncError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: Any = None):
        self.code = code
        self.details = details
        super().__init__(message)


@dataclass(frozen=True)
class ActionCatalogSyncResult:
    status: str
    contract_version: str | None = None
    fingerprint: str | None = None
    remote_count: int = 0
    drift: tuple[str, ...] = ()


_SYNC_CONTEXT: ContextVar[tuple[str, ActionCatalogSyncResult] | None] = ContextVar(
    "kodagent_action_catalog_sync", default=None
)


def action_catalog_sync_enabled() -> bool:
    # The production contract is synchronized by default.  Offline/library
    # callers can explicitly opt out with ``OA_AGENT_ACTION_CATALOG_SYNC=false``.
    return os.getenv("OA_AGENT_ACTION_CATALOG_SYNC", "true").strip().lower() in {
        "1", "true", "yes", "on"
    }


def action_catalog_strict() -> bool:
    return os.getenv("OA_AGENT_ACTION_CATALOG_STRICT", "true").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _local_contract() -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for action in ACTION_SPECS:
        fields = action_field_specs(action, use_runtime=False)
        values[action.action_id] = {
            "actionId": action.action_id,
            "capabilityId": action.capability_id,
            "executionClass": action.execution_class,
            "operation": action.operation,
            "readOnly": action.read_only,
            "requiresConfirmation": action.requires_confirmation,
            "description": action.description,
            "permission": (
                action.permission
                if action.permission != "agent:read"
                else (get_tool_contract(action.execution_tool).permission if action.execution_tool else "agent:read")
            ),
            "requiredFields": sorted(action_required_fields(action, use_runtime=False)),
            "constraints": [dict(value) for value in action_constraints(action, use_runtime=False)],
            "fields": sorted(
                [
                    {
                        "name": field.name,
                        "type": field.field_type,
                        "required": field.required,
                        "nullable": field.nullable,
                        "description": field.description,
                        "sourcePolicy": field.source_policy,
                        "format": field.format,
                        "enum": [str(value) for value in field.enum],
                    }
                    for field in fields
                ],
                key=lambda value: value["name"],
            ),
        }
    return values


def _remote_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("data"), dict):
        payload = payload["data"]
    actions = payload.get("actions") if isinstance(payload, dict) else None
    if not isinstance(actions, list):
        raise ActionCatalogSyncError(
            "ACTION_CATALOG_INVALID", "Java 动作契约缺少 actions 数组", details=payload
        )
    return {"contractVersion": payload.get("contractVersion"), "actions": actions}


def _canonical_remote_action(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ActionCatalogSyncError("ACTION_CATALOG_INVALID", "Java 动作契约包含非对象项")
    action_id = str(item.get("actionId") or "").strip()
    if not action_id:
        raise ActionCatalogSyncError("ACTION_CATALOG_INVALID", "Java 动作契约包含空 actionId")
    fields = item.get("fields") or []
    if not isinstance(fields, list):
        raise ActionCatalogSyncError("ACTION_CATALOG_INVALID", f"动作 {action_id} 的 fields 不是数组")
    normalized_fields = []
    field_names: set[str] = set()
    for field in fields:
        if not isinstance(field, dict) or not str(field.get("name") or "").strip():
            raise ActionCatalogSyncError("ACTION_CATALOG_INVALID", f"动作 {action_id} 的字段定义无效")
        field_name = str(field.get("name")).strip()
        if field_name in field_names:
            raise ActionCatalogSyncError("ACTION_CATALOG_INVALID", f"动作 {action_id} 的字段重复：{field_name}")
        field_names.add(field_name)
        enum_values = [str(value) for value in (field.get("enum") or ())]
        if len(enum_values) != len(set(enum_values)):
            raise ActionCatalogSyncError("ACTION_CATALOG_INVALID", f"动作 {action_id} 的枚举值重复：{field_name}")
        normalized_fields.append({
            "name": field_name,
            "type": str(field.get("type") or "any"),
            "required": bool(field.get("required", False)),
            "nullable": bool(field.get("nullable", not field.get("required", False))),
            "description": str(field.get("description") or ""),
            "sourcePolicy": str(field.get("sourcePolicy") or "user_input"),
            "format": field.get("format"),
            "enum": enum_values,
        })
    declared_required = sorted(str(value) for value in (item.get("requiredFields") or []))
    derived_required = sorted(
        field["name"] for field in normalized_fields if field["required"]
    )
    if declared_required != derived_required:
        raise ActionCatalogSyncError(
            "ACTION_CATALOG_INVALID",
            f"动作 {action_id} 的 requiredFields 与 fields.required 不一致",
            details={"declared": declared_required, "derived": derived_required},
        )
    constraints = item.get("constraints") or []
    if not isinstance(constraints, list) or any(not isinstance(value, dict) for value in constraints):
        raise ActionCatalogSyncError(
            "ACTION_CATALOG_INVALID", f"动作 {action_id} 的 constraints 不是对象数组"
        )
    return {
        "actionId": action_id,
        "capabilityId": str(item.get("capabilityId") or ""),
        "executionClass": str(item.get("executionClass") or ""),
        "operation": str(item.get("operation") or ""),
        "readOnly": bool(item.get("readOnly", True)),
        "requiresConfirmation": bool(item.get("requiresConfirmation", False)),
        "permission": str(item.get("permission") or ""),
        "requiredFields": sorted(str(value) for value in (item.get("requiredFields") or [])),
        "constraints": [dict(value) for value in constraints],
        "fields": sorted(normalized_fields, key=lambda value: value["name"]),
        "description": str(item.get("description") or ""),
    }


def _fingerprint(values: list[dict[str, Any]]) -> str:
    encoded = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _compare(remote: list[dict[str, Any]]) -> tuple[str, ...]:
    """Validate the executable binding, not duplicate Java's schema.

    The Java catalog is authoritative for action existence and all business
    metadata (fields, required fields, constraints, descriptions and
    permissions).  Python is only an executor-binding table.  Therefore a
    Java-only action is valid catalog data and is surfaced at planning time as
    ``ACTION_EXECUTOR_BINDING_MISSING``; it must not be treated as drift.
    Conversely, a local action omitted by Java is hidden by the runtime
    snapshot and is not executable.  Only metadata that affects whether the
    local executor is safe to invoke is compared here.
    """
    local = _local_contract()
    issues: list[str] = []
    remote_map: dict[str, dict[str, Any]] = {}
    for item in remote:
        action_id = item["actionId"]
        if action_id in remote_map:
            issues.append(f"远端动作重复：{action_id}")
        remote_map[action_id] = item
    local_ids = set(local)
    remote_ids = set(remote_map)
    # These fields affect whether the bound executor can safely call Java.
    # Business fields/constraints/descriptions remain Java-owned overlays, but
    # a permission change must fail closed because the Python HTTP contract
    # is what actually places X-Agent-Permission on the request.
    comparable = (
        "capabilityId", "executionClass", "operation", "readOnly",
        "requiresConfirmation", "permission",
    )
    for action_id in sorted(local_ids & remote_ids):
        for key in comparable:
            if local[action_id].get(key) != remote_map[action_id].get(key):
                issues.append(
                    f"动作 {action_id} 字段漂移：{key} local={local[action_id].get(key)!r} remote={remote_map[action_id].get(key)!r}"
                )
        # Do not compare fields, requiredFields, constraints or descriptions
        # here. Those values are deliberately overlaid from the validated Java
        # snapshot and are the source of truth for compilation.
    return tuple(issues)


def sync_action_catalog(*, run_id: str | None = None, force: bool = False) -> ActionCatalogSyncResult:
    """Fetch and validate the Java contract once per Run."""
    context = str(run_id or os.getenv("OA_AGENT_RUN_ID") or "")
    cached = _SYNC_CONTEXT.get()
    if cached and cached[0] == context and not force:
        return cached[1]
    if not action_catalog_sync_enabled():
        clear_runtime_action_catalog()
        result = ActionCatalogSyncResult(status="SKIPPED", remote_count=0)
        _SYNC_CONTEXT.set((context, result))
        return result
    # A process with no configured Java base URL is an intentional offline
    # library invocation.  Keep the production default strict, while avoiding
    # a surprising localhost network call for unit tests and reusable imports.
    # An explicit environment setting always wins (the tests and deployments
    # that want synchronization provide OA_AGENT_ACTION_CATALOG_SYNC=true).
    if "OA_AGENT_ACTION_CATALOG_SYNC" not in os.environ and not os.getenv("OA_AGENT_BASE_URL"):
        clear_runtime_action_catalog()
        result = ActionCatalogSyncResult(status="SKIPPED", remote_count=0)
        _SYNC_CONTEXT.set((context, result))
        return result
    try:
        payload = _remote_payload(get_agent_action_catalog())
        remote = [_canonical_remote_action(item) for item in payload["actions"]]
        issues = _compare(remote)
        fingerprint = _fingerprint(sorted(remote, key=lambda value: value["actionId"]))
        if issues:
            clear_runtime_action_catalog()
            result = ActionCatalogSyncResult(
                status="DRIFT", contract_version=payload.get("contractVersion"),
                fingerprint=fingerprint, remote_count=len(remote), drift=issues,
            )
            if action_catalog_strict():
                raise ActionCatalogSyncError(
                    "ACTION_CATALOG_DRIFT", "Java/Python Agent 动作契约不一致，已阻止本次 Run", details=list(issues)
                )
            _SYNC_CONTEXT.set((context, result))
            return result
        # The validated Java snapshot is the runtime contract for this Run.
        # Python keeps only the executor binding; field schemas and visible
        # action metadata are overlaid from this snapshot by capabilities.py.
        set_runtime_action_catalog(
            remote, contract_version=payload.get("contractVersion"), fingerprint=fingerprint
        )
        result = ActionCatalogSyncResult(
            status="SYNCED", contract_version=payload.get("contractVersion"),
            fingerprint=fingerprint, remote_count=len(remote),
        )
        _SYNC_CONTEXT.set((context, result))
        return result
    except ActionCatalogSyncError:
        raise
    except Exception as exc:
        clear_runtime_action_catalog()
        if action_catalog_strict():
            raise ActionCatalogSyncError(
                "ACTION_CATALOG_UNAVAILABLE", "无法读取 Java Agent 动作契约，已阻止本次 Run", details=str(exc)
            ) from exc
        result = ActionCatalogSyncResult(status="UNAVAILABLE")
        _SYNC_CONTEXT.set((context, result))
        return result


__all__ = [
    "ActionCatalogSyncError", "ActionCatalogSyncResult", "action_catalog_strict",
    "action_catalog_sync_enabled", "sync_action_catalog",
]
