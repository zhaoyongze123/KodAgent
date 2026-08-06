"""Transport/schema normalization at the action boundary."""

from __future__ import annotations

from typing import Any


_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "meeting.create": {
        "subject": ("title", "meeting_subject"), "start_time": ("startTime", "start"),
        "end_time": ("endTime", "end"), "attendees": ("attendee_names", "participants"),
        "room_capacity": ("capacity",), "remark": ("notes", "remark_text"),
    },
    "meeting.update": {
        "source_booking_id": ("sourceBookingId", "booking_id", "bookingId"),
        "subject": ("title", "meeting_subject"), "start_time": ("startTime", "start"),
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
    return values


__all__ = ["normalize_action_payload"]
