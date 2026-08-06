"""Compile-time validation for registered business-action parameters.

The LLM extracts values; this module decides whether those values satisfy the
registered action contract.  Workflow implementations remain responsible for
business rules such as conflict checks, but they no longer need to repeat the
basic action/field/type/source checks at every entry point.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from .capabilities import ActionFieldSpec, ActionSpec, action_constraints, action_field_specs


class ActionValidationResult:
    def __init__(self, *, missing: list[str] | None = None,
                 invalid: list[str] | None = None,
                 forbidden: list[str] | None = None):
        self.missing_fields = list(missing or [])
        self.invalid_fields = list(invalid or [])
        self.forbidden_fields = list(forbidden or [])

    @property
    def ok(self) -> bool:
        return not (self.missing_fields or self.invalid_fields or self.forbidden_fields)

    @property
    def issues(self) -> list[str]:
        issues: list[str] = []
        issues.extend(f"缺少必填字段：{name}" for name in self.missing_fields)
        issues.extend(f"字段值无效：{name}" for name in self.invalid_fields)
        issues.extend(f"禁止传入执行字段：{name}" for name in self.forbidden_fields)
        return issues


_FORBIDDEN_KEYS = {
    "tool", "tool_name", "toolName", "execution_tool", "executionTool",
    "java_path", "javaPath", "url", "path", "sql", "table",
}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _present(payload: dict[str, Any], field: ActionFieldSpec) -> bool:
    value = payload.get(field.name)
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _type_ok(value: Any, field: ActionFieldSpec) -> bool:
    if value is None:
        return field.nullable
    kind = field.field_type
    if kind in {"any", "object"}:
        return isinstance(value, dict) if kind == "object" else True
    if kind == "string":
        return isinstance(value, str) and bool(value.strip())
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool) or (
            isinstance(value, str) and value.strip().isdigit()
        )
    if kind == "number":
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return True
        if isinstance(value, str):
            try:
                float(value.strip())
                return bool(value.strip())
            except ValueError:
                return False
        return False
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "array":
        return isinstance(value, list)
    if kind == "date":
        if not isinstance(value, str) or not _DATE_RE.fullmatch(value.strip()):
            return False
        try:
            date.fromisoformat(value.strip())
            return True
        except ValueError:
            return False
    if kind == "datetime":
        if not isinstance(value, str) or not value.strip():
            return False
        normalized = value.strip().replace("Z", "+00:00")
        # ``datetime.fromisoformat`` accepts a bare date as midnight. A
        # business datetime field must carry an explicit time component.
        if "T" not in normalized and " " not in normalized:
            return False
        try:
            datetime.fromisoformat(normalized)
            return True
        except ValueError:
            return False
    return True


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _present_value(values: dict[str, Any], key: str) -> bool:
    value = values.get(key)
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _validate_declared_constraints(
    action: ActionSpec, values: dict[str, Any], result: ActionValidationResult
) -> None:
    """Interpret portable constraints from the Java action contract.

    This layer intentionally performs only structural validation.  It cannot
    decide whether a meeting room is free, whether a record is editable, or
    whether the caller has permission; those remain domain/Java concerns.
    """
    for constraint in action_constraints(action):
        kind = str(constraint.get("type") or "").strip().lower()
        if kind == "interval":
            start_name = str(constraint.get("start") or "").strip()
            end_name = str(constraint.get("end") or "").strip()
            if not start_name or not end_name:
                continue
            has_start = _present_value(values, start_name)
            has_end = _present_value(values, end_name)
            if has_start != has_end:
                result.invalid_fields.append(f"{start_name}/{end_name}(必须同时提供)")
            elif has_start and has_end:
                start = _parse_datetime(values.get(start_name))
                end = _parse_datetime(values.get(end_name))
                if start is not None and end is not None and end <= start:
                    result.invalid_fields.append(f"{start_name}/{end_name}(结束时间必须晚于开始时间)")
        elif kind == "paired":
            names = [str(value).strip() for value in (constraint.get("fields") or [])]
            active = [_present_value(values, name) for name in names]
            if any(active) and not all(active):
                result.invalid_fields.append(f"{'/'.join(names)}(必须同时提供)")
        elif kind == "exclusive_groups":
            groups = constraint.get("groups") or []
            active_groups = []
            for group in groups:
                names = [str(value).strip() for value in (group or [])]
                if any(_present_value(values, name) for name in names):
                    active_groups.append(names)
            if len(active_groups) > 1:
                result.invalid_fields.append("查询条件(不能同时提供)")
        elif kind == "at_least_one":
            names = [str(value).strip() for value in (constraint.get("fields") or [])]
            # A follow-up UPDATE may intentionally carry only an authorized
            # source ID; the workflow extracts the changed fields from the
            # trusted current-user message/checkpoint.  Do not turn that
            # state-bound handoff into a false no-op validation failure.
            if names and not any(_present_value(values, name) for name in names) and not authorized_source_fields(values):
                result.invalid_fields.append("更新内容(至少提供一个要修改的字段)")
        elif kind in {"non_empty_unique", "non_empty_if_present"}:
            field_name = str(constraint.get("field") or "").strip()
            if not field_name or field_name not in values or values.get(field_name) is None:
                continue
            value = values.get(field_name)
            if not isinstance(value, list):
                continue
            if not value:
                result.invalid_fields.append(f"{field_name}(不能为空)")
                continue
            if kind == "non_empty_unique":
                normalized = [str(item).strip() for item in value]
                if any(not item for item in normalized):
                    result.invalid_fields.append(f"{field_name}(不能包含空编号)")
                if len(normalized) != len(set(normalized)):
                    result.invalid_fields.append(f"{field_name}(不能重复)")
        elif kind == "requires_if_present":
            field_name = str(constraint.get("field") or "").strip()
            if not field_name or not _present_value(values, field_name):
                continue
            for required_name in (constraint.get("requires") or []):
                required_name = str(required_name).strip()
                if required_name and not _present_value(values, required_name):
                    result.invalid_fields.append(
                        f"{required_name}(使用{field_name}条件时必须提供)"
                    )


def _validate_cross_fields(
    action: ActionSpec,
    values: dict[str, Any],
    result: ActionValidationResult,
    *,
    authorized_fields: set[str] | None = None,
) -> None:
    """Validate relationships that cannot be represented by one field.

    This is intentionally the shared contract layer: workflows still own
    conflict checks, authorization, and domain-specific policy, while this
    function rejects structurally impossible plans before a tool call.
    """
    action_id = action.action_id
    _validate_declared_constraints(action, values, result)

    # Lists that identify records or participants must not be empty.  Filters
    # and optional equipment are allowed to be empty because they represent
    # an omitted constraint rather than a target set.
    # ``attendees`` is optional for a meeting: the workflow resolves the
    # authenticated organizer as the implicit participant.  The other lists
    # identify an explicit target set and therefore cannot be supplied empty.
    for field_name in ("taskIds", "targets", "attachment_file_ids"):
        value = values.get(field_name)
        if field_name in values and value is not None and isinstance(value, list) and not value:
            result.invalid_fields.append(f"{field_name}(不能为空)")
    task_ids = values.get("taskIds")
    if isinstance(task_ids, list):
        if any(item is None or (isinstance(item, str) and not item.strip()) for item in task_ids):
            result.invalid_fields.append("taskIds(不能包含空编号)")
        normalized = [str(item).strip() for item in task_ids]
        if len(normalized) != len(set(normalized)):
            result.invalid_fields.append("taskIds(不能重复)")

    # Every interval is a closed input contract.  A single endpoint is not a
    # usable range, and an end before/equal to a start is always invalid.
    interval_pairs = {
        "meeting.create": ("start_time", "end_time"),
        "meeting.update": ("start_time", "end_time"),
        "schedule.create": ("start_time", "end_time"),
        "schedule.update": ("start_time", "end_time"),
        "reporting.meeting": ("start_time", "end_time"),
        "reporting.schedule": ("start_time", "end_time"),
        "reporting.party_file": ("start_time", "end_time"),
    }
    if action_id in interval_pairs:
        start_name, end_name = interval_pairs[action_id]
        has_start = _present_value(values, start_name)
        has_end = _present_value(values, end_name)
        if has_start != has_end:
            result.invalid_fields.append(f"{start_name}/{end_name}(必须同时提供)")
        elif has_start and has_end:
            start = _parse_datetime(values.get(start_name))
            end = _parse_datetime(values.get(end_name))
            if start is not None and end is not None and end <= start:
                result.invalid_fields.append(f"{start_name}/{end_name}(结束时间必须晚于开始时间)")

    if action_id == "schedule.query":
        has_date = _present_value(values, "date")
        has_start = _present_value(values, "start_time")
        has_end = _present_value(values, "end_time")
        if has_date and (has_start or has_end):
            result.invalid_fields.append("date与start_time/end_time(不能同时提供)")
        if has_start != has_end:
            result.invalid_fields.append("start_time/end_time(必须同时提供)")

    # UPDATE is meaningful only if at least one mutable field is present.  A
    # source ID alone would otherwise create a no-op draft or, worse, be
    # interpreted by a provider as a new record.
    mutable_fields = {
        "meeting.update": ("start_time", "end_time", "subject", "attendees", "room_preference", "equipment", "room_capacity", "remark"),
        "schedule.update": ("title", "start_time", "end_time", "description", "location", "attendees", "other_participants"),
        "party_file.update": ("title", "content", "category_name", "summary", "attachment_file_ids"),
    }.get(action_id)
    # A follow-up turn may carry only the authorized source ID here; the
    # workflow tool then extracts the changed fields from the current user
    # message and working-memory snapshot.  Enforce the no-op rule for a
    # standalone model plan, but do not reject that state-bound handoff.
    if (
        mutable_fields
        and not any(_present_value(values, name) for name in mutable_fields)
        and not (authorized_fields or set())
    ):
        result.invalid_fields.append("更新内容(至少提供一个要修改的字段)")

    if action_id == "reporting.approval":
        has_from = _present_value(values, "created_from")
        has_to = _present_value(values, "created_to")
        if has_from != has_to:
            result.invalid_fields.append("created_from/created_to(必须同时提供)")
        amount_operator = str(values.get("amount_operator") or "").strip().upper()
        if amount_operator and not _present_value(values, "amount"):
            result.invalid_fields.append("amount(使用金额条件时必须提供)")
        if _present_value(values, "amount") and not amount_operator:
            result.invalid_fields.append("amount_operator(使用金额条件时必须提供)")
        if has_from and has_to:
            try:
                if date.fromisoformat(str(values["created_from"])) > date.fromisoformat(str(values["created_to"])):
                    result.invalid_fields.append("created_from/created_to(开始日期不能晚于结束日期)")
            except ValueError:
                # The field-level validator owns malformed-date reporting.
                pass

    # Shared numeric bounds keep pagination, retrieval and capacity requests
    # finite and positive before they reach a backend service.
    bounds = {
        "limit": (1, 50),
        "top_k": (1, 50),
        "room_capacity": (1, 100000),
        "min_pending_days": (0, 36500),
    }
    for field_name, (minimum, maximum) in bounds.items():
        if field_name not in values or values.get(field_name) in (None, ""):
            continue
        try:
            numeric = int(values[field_name])
        except (TypeError, ValueError):
            continue  # _type_ok owns the type error.
        if numeric < minimum or numeric > maximum:
            result.invalid_fields.append(f"{field_name}(必须在 {minimum} 到 {maximum} 之间)")

    # IDs are database/business identifiers. Authorization is checked
    # separately; this guard only rejects structurally impossible values.
    for field_name in ("source_booking_id", "source_schedule_id", "source_party_file_id",
                       "left_file_id", "right_file_id", "file_id"):
        if field_name not in values or values.get(field_name) in (None, ""):
            continue
        try:
            if int(values[field_name]) <= 0:
                result.invalid_fields.append(f"{field_name}(必须为正整数)")
        except (TypeError, ValueError):
            pass


def validate_action_payload(action: ActionSpec, payload: dict[str, Any] | None,
                             *, authorized_source_fields: set[str] | None = None) -> ActionValidationResult:
    """Validate an action payload without executing business code.

    ``authorized_source_fields`` is supplied by the route boundary after it
    resolves a current-user query fact.  A model-supplied ID cannot satisfy an
    ``authorized_query_fact`` field by merely writing the same JSON key.
    """
    values = dict(payload or {})
    result = ActionValidationResult()
    specs = action_field_specs(action)
    for field in specs:
        if field.required and not _present(values, field):
            result.missing_fields.append(field.name)
            continue
        if field.name in values and values[field.name] is not None and not _type_ok(values[field.name], field):
            result.invalid_fields.append(field.name)
            continue
        if field.name in values and field.enum and str(values[field.name]).upper() not in field.enum:
            result.invalid_fields.append(field.name)
            continue
        if field.source_policy == "authorized_query_fact" and _present(values, field):
            authorized = authorized_source_fields or set()
            if field.name not in authorized:
                result.invalid_fields.append(f"{field.name}(必须来自当前用户授权查询事实)")
    result.forbidden_fields.extend(sorted(key for key in values if key in _FORBIDDEN_KEYS))
    _validate_cross_fields(
        action,
        values,
        result,
        # A caller-provided authorization set proves the source ID is
        # authorized, but it does not prove that this is a state-bound
        # follow-up carrying the user's requested mutation.  Only the
        # internal marker injected by the route boundary may bypass the
        # standalone UPDATE no-op check.
        authorized_fields={
            str(item) for item in (values.get("_authorized_source_fields") or ())
        } if isinstance(values.get("_authorized_source_fields"), (list, tuple, set)) else set(),
    )
    # A single malformed provider response should never produce the same
    # user-facing issue multiple times when both a declarative contract and a
    # legacy compatibility check describe the same relationship.
    result.missing_fields[:] = list(dict.fromkeys(result.missing_fields))
    result.invalid_fields[:] = list(dict.fromkeys(result.invalid_fields))
    result.forbidden_fields[:] = list(dict.fromkeys(result.forbidden_fields))
    return result


def authorized_source_fields(payload: dict[str, Any] | None) -> set[str]:
    marker = (payload or {}).get("_authorized_source_fields")
    if isinstance(marker, (list, tuple, set)):
        return {str(item) for item in marker}
    return set()


__all__ = ["ActionValidationResult", "authorized_source_fields", "validate_action_payload"]
