from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


PersonalScheduleWorkflowStatus = Literal["NEEDS_INPUT", "DRAFT_READY", "FAILED"]


class PersonalScheduleWorkflowInput(BaseModel):
    operation: Literal["CREATE", "UPDATE", "CANCEL"]
    title: str = ""
    start_time: str = ""
    end_time: str = ""
    source_schedule_id: int | None = None
    location: str = ""
    description: str = ""
    attendee_user_ids: list[int] = Field(default_factory=list)
    other_participants: str = ""


class PersonalScheduleWorkflowOutcome(BaseModel):
    status: PersonalScheduleWorkflowStatus
    message: str
    draft_id: str | None = None
    approval_id: str | None = None
    confirmation_token: str | None = None
    facts: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    retryable: bool = False
