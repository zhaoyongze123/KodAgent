"""Typed read models at the boundaries of the four OA domains.

The Java Facade remains the write authority.  These models intentionally allow
unknown response fields so an OA version can add metadata without breaking the
Agent, while giving orchestration and presentation stable names for the facts
they are allowed to consume.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OAReadModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class PartyFileAttachment(OAReadModel):
    id: int | str | None = None
    file_id: int | str | None = Field(default=None, alias="fileId")
    name: str = ""
    file_name: str = Field(default="", alias="fileName")
    content_type: str = Field(default="", alias="contentType")
    size: int | None = None
    preview_url: str = Field(default="", alias="previewUrl")
    download_url: str = Field(default="", alias="downloadUrl")


class PartyFile(OAReadModel):
    id: int | str | None = None
    title: str = ""
    category_id: int | str | None = Field(default=None, alias="categoryId")
    category_name: str = Field(default="", alias="categoryName")
    publish_time: datetime | str | None = Field(default=None, alias="publishTime")
    status: int | str | None = None
    status_label: str = Field(default="", alias="statusLabel")
    attachments: list[PartyFileAttachment] = Field(default_factory=list)


class ApprovalRequest(OAReadModel):
    id: int | str | None = None
    approval_id: int | str | None = Field(default=None, alias="approvalId")
    draft_id: int | str | None = Field(default=None, alias="draftId")
    process_instance_id: str = Field(default="", alias="processInstanceId")
    process_definition_name: str = Field(default="", alias="processDefinitionName")
    status: str = ""
    start_time: datetime | str | None = Field(default=None, alias="startTime")


class ApprovalTask(OAReadModel):
    id: int | str | None = None
    task_id: int | str | None = Field(default=None, alias="taskId")
    process_instance_id: str = Field(default="", alias="processInstanceId")
    process_definition_name: str = Field(default="", alias="processDefinitionName")
    task_name: str = Field(default="", alias="taskName")
    status: str = ""
    create_time: datetime | str | None = Field(default=None, alias="createTime")


class ScheduleEntry(OAReadModel):
    id: int | str | None = None
    schedule_id: int | str | None = Field(default=None, alias="scheduleId")
    title: str = ""
    start_time: datetime | str | None = Field(default=None, alias="startTime")
    end_time: datetime | str | None = Field(default=None, alias="endTime")
    editable: bool = False
    source_type: str = Field(default="", alias="sourceType")


class CalendarEvent(ScheduleEntry):
    event_type: str = Field(default="", alias="eventType")
    location: str = ""


def model_dump_oa(value: OAReadModel | dict[str, Any]) -> dict[str, Any]:
    """Normalize one OA response object without leaking model internals."""
    model = value if isinstance(value, OAReadModel) else OAReadModel.model_validate(value)
    return model.model_dump(by_alias=True, exclude_none=True)


__all__ = [
    "ApprovalRequest",
    "ApprovalTask",
    "CalendarEvent",
    "OAReadModel",
    "PartyFile",
    "PartyFileAttachment",
    "ScheduleEntry",
    "model_dump_oa",
]
