"""Transport/schema normalization at the action boundary.

This module is the compile layer between a model proposal and the action
contract.  Alias mapping, array splitting, type coercion and datetime
completion all happen here, before validation.  Values that can be repaired
from the information already supplied are rewritten in place; validation then
sees only genuinely unresolvable input or business-rule violations.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from ..capabilities import action_field_specs


_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "meeting.create": {
        "subject": ("title", "topic", "meeting_subject"), "start_time": ("startTime", "start"),
        "end_time": ("endTime", "end"), "attendees": ("attendee_names", "participants"),
        "room_capacity": ("capacity",), "remark": ("notes", "remark_text"),
    },
    "meeting.update": {
        "source_booking_id": ("sourceBookingId", "booking_id", "bookingId"),
        "subject": ("title", "topic", "meeting_subject"), "start_time": ("startTime", "start"),
        "end_time": ("endTime", "end"), "attendees": ("attendee_names", "participants"),
        "room_capacity": ("capacity",), "remark": ("notes", "remark_text"),
    },
    "meeting.cancel": {"source_booking_id": ("sourceBookingId", "booking_id", "bookingId")},
    "schedule.create": {
        "title": ("summary", "subject"), "start_time": ("startTime", "start"),
        "end_time": ("endTime", "end"), "attendees": ("attendee_user_ids", "participants"),
        "other_participants": ("otherParticipants",),
    },
    "schedule.update": {
        "source_schedule_id": ("sourceScheduleId", "schedule_id", "scheduleId"),
        "title": ("summary", "subject"), "start_time": ("startTime", "start"),
        "end_time": ("endTime", "end"), "attendees": ("attendee_user_ids", "participants"),
        "other_participants": ("otherParticipants",),
    },
    "schedule.cancel": {"source_schedule_id": ("sourceScheduleId", "schedule_id", "scheduleId")},
    "schedule.query": {"time_range": ("timeRange",)},
    "party_file.create": {
        "title": ("file_title", "document_title"), "content": ("body", "正文", "text"),
        "category_name": ("category", "categoryName", "category_type", "document_type"),
        "publish_time": ("publishTime",), "targets": ("distribution", "distribution_targets", "target_users"),
        "distribute_to_self": ("distributeToSelf", "send_to_self"),
        "attachment_file_ids": ("attachmentFileIds", "attachments"), "summary": ("abstract", "summary_text"),
    },
    "party_file.update": {
        "source_party_file_id": ("sourcePartyFileId", "party_file_id", "partyFileId"),
        "title": ("file_title", "document_title"), "content": ("body", "正文", "text"),
        "category_name": ("category", "categoryName", "document_type"),
        "summary": ("abstract", "summary_text"), "attachment_file_ids": ("attachmentFileIds", "attachments"),
    },
    "party_file.delete": {"source_party_file_id": ("sourcePartyFileId", "party_file_id", "partyFileId")},
    "party_file.attachments": {"source_party_file_id": ("sourcePartyFileId", "party_file_id", "partyFileId")},
    "approval.process.application_detail": {"processInstanceId": ("process_instance_id", "processId")},
    "approval.process.withdraw": {"processInstanceId": ("process_instance_id", "processId")},
}


_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATE_SEP_RE = re.compile(r"^(\d{4})[年./\-](\d{1,2})[月./\-](\d{1,2})日?$")
_TIME_ONLY_RE = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?$")
_INTEGER_RE = re.compile(r"^[+-]?\d+$")
_NUMERIC_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")
_DATETIME_TZ_RE = re.compile(r"([+-]\d{2}:?\d{2}|Z|z)$")
_TRUTHY = frozenset({"true", "yes", "y", "1", "是"})
_FALSY = frozenset({"false", "no", "n", "0", "否", ""})


def _normalize_time_text(text: str) -> str | None:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", str(text or "").strip())
    if match is None:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    second = int(match.group(3)) if match.group(3) else 0
    if hour > 23 or minute > 59 or second > 59:
        return None
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def _normalize_date_text(text: str) -> str | None:
    text = str(text or "").strip()
    if not text:
        return None
    if _DATE_ONLY_RE.fullmatch(text):
        try:
            date.fromisoformat(text)
        except ValueError:
            return None
        return text
    match = _DATE_SEP_RE.fullmatch(text)
    if match is None:
        return None
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    normalized = f"{year:04d}-{month:02d}-{day:02d}"
    try:
        date.fromisoformat(normalized)
    except ValueError:
        return None
    return normalized


def _normalize_datetime_text(text: str) -> str | None:
    """Render a datetime string as ``yyyy-MM-dd HH:mm:ss`` when possible.

    Accepts ISO ``T`` separators, date-only values (completed as midnight),
    and timezone suffixes, which are preserved verbatim.  Unparsable relative
    text (``明天下午``) stays untouched so validation reports it.
    """
    text = str(text or "").strip().replace("T", " ").replace("t", " ")
    if not text:
        return None
    timezone = ""
    suffix = _DATETIME_TZ_RE.search(text)
    if suffix:
        timezone = suffix.group(1)
        text = text[: suffix.start()].strip()
    date_text, separator, time_text = text.partition(" ")
    normalized_date = _normalize_date_text(date_text)
    if normalized_date is None:
        return None
    if not separator:
        return f"{normalized_date} 00:00:00"
    normalized_time = _normalize_time_text(time_text)
    if normalized_time is None:
        return None
    if timezone in {"Z", "z"}:
        timezone = "+00:00"
    return f"{normalized_date} {normalized_time}{timezone}"


def _schema_normalize(action: Any, values: dict[str, Any]) -> None:
    """Coerce declared fields to their schema type, absorbing fixable drift.

    A time-only datetime value (``08:00``) is completed with the payload's
    ``date`` key or the date carried by a sibling datetime field; a redundant
    ``date`` key is removed once its information is absorbed.  Bare dates are
    completed as midnight so the business layer can apply its own rules
    (for example rejecting an off-hours booking) instead of a format error.
    """
    specs = {field.name: field for field in action_field_specs(action)}
    date_value = values.get("date")
    datetime_names = [
        name for name, field in specs.items() if str(field.field_type).strip().lower() == "datetime"
    ]

    for name in datetime_names:
        raw = values.get(name)
        if not isinstance(raw, str) or not _TIME_ONLY_RE.fullmatch(raw.strip()):
            continue
        normalized_time = _normalize_time_text(raw)
        if normalized_time is None:
            continue
        date_source = _normalize_date_text(date_value) if isinstance(date_value, str) else None
        if date_source is None:
            for other in datetime_names:
                if other == name:
                    continue
                sibling = values.get(other)
                if not isinstance(sibling, str):
                    continue
                candidate = _normalize_datetime_text(sibling)
                if candidate is not None:
                    date_source = candidate[:10]
                    break
        if date_source is not None:
            values[name] = f"{date_source} {normalized_time}"
            if isinstance(date_value, str):
                values.pop("date", None)
                date_value = None
        else:
            # No date source: keep the time-only value but normalize its
            # spelling (``8:00`` -> ``08:00:00``) so the missing date is the
            # only remaining issue reported to the model.
            values[name] = normalized_time

    for name, field in specs.items():
        if name not in values:
            continue
        value = values[name]
        kind = str(field.field_type).strip().lower()
        if kind == "datetime" and isinstance(value, str):
            normalized = _normalize_datetime_text(value)
            if normalized is not None:
                values[name] = normalized
        elif kind == "date" and isinstance(value, str):
            normalized = _normalize_date_text(value)
            if normalized is not None:
                values[name] = normalized
        elif kind == "integer" and isinstance(value, str):
            if _INTEGER_RE.fullmatch(value.strip()):
                values[name] = int(value.strip())
        elif kind == "number" and isinstance(value, str):
            if _NUMERIC_RE.fullmatch(value.strip()):
                numeric = float(value.strip())
                values[name] = int(numeric) if numeric.is_integer() else numeric
        elif kind == "boolean" and isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in _TRUTHY:
                values[name] = True
            elif lowered in _FALSY:
                values[name] = False
        if field.enum and isinstance(values[name], str):
            upper = values[name].strip().upper()
            if upper in field.enum:
                values[name] = upper


def normalize_action_payload(action: Any, payload: dict[str, Any] | None) -> dict[str, Any]:
    values = dict(payload or {})
    for canonical_name, aliases in _ALIASES.get(str(getattr(action, "action_id", "")), {}).items():
        if values.get(canonical_name) not in (None, "", [], {}):
            continue
        for alias in aliases:
            if values.get(alias) not in (None, "", [], {}):
                values[canonical_name] = values[alias]
                break
    nested = values.get("content_details") or values.get("contentDetails")
    if isinstance(nested, dict):
        for name in ("title", "content", "publish_time", "targets"):
            if values.get(name) in (None, "", [], {}):
                alias = "publishTime" if name == "publish_time" else name
                if nested.get(alias) not in (None, "", [], {}):
                    values[name] = nested[alias]
        if values.get("title") in (None, "", [], {}) and nested.get("document_title"):
            values["title"] = nested["document_title"]
    attachments = values.get("attachment_file_ids")
    if isinstance(attachments, str) and attachments.strip():
        values["attachment_file_ids"] = [item.strip() for item in attachments.split(",") if item.strip()]
    targets = values.get("targets")
    if isinstance(targets, str) and targets.strip():
        values["targets"] = [item.strip() for item in targets.split(",") if item.strip()]

    # Providers sometimes serialize a schema-declared array as one text value.
    # Normalize that transport representation from the Java-owned field schema
    # before validation; domain workflows still own the meaning of each item.
    array_fields = {
        field.name for field in action_field_specs(action) if field.field_type == "array"
    }
    for field_name in array_fields:
        value = values.get(field_name)
        if isinstance(value, str) and value.strip():
            values[field_name] = [
                item.strip()
                for item in re.split(r"[,，、;；\n]+", value)
                if item.strip()
            ]

    _schema_normalize(action, values)
    return values


__all__ = ["normalize_action_payload"]
