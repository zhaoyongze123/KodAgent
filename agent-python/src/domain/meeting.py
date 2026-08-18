"""Structured models used by the meeting-room business flow."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class MeetingBookingRequest(BaseModel):
    """A normalized meeting request, independent from model wording."""

    intent: Literal["meeting_booking"] = "meeting_booking"
    subject: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    attendee_user_ids: list[int] = Field(default_factory=list)
    attendee_user_names: list[str] = Field(default_factory=list)
    room_capacity: int | None = Field(default=None, ge=1)
    equipment: list[str] = Field(default_factory=list)
    room_preference: str | None = None
    remark: str = ""
    conflict_policy: Literal["block", "allow_with_warning"] = "block"


class RequestValidation(BaseModel):
    """Validation output shown to the Agent for the next action."""

    valid: bool
    missing_fields: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    request: MeetingBookingRequest | None = None
