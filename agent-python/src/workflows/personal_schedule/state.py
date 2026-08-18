from __future__ import annotations

from typing import Any

from typing_extensions import TypedDict


class PersonalScheduleWorkflowState(TypedDict, total=False):
    operation: str
    title: str
    start_time: str
    end_time: str
    source_schedule_id: int | None
    location: str
    description: str
    attendee_user_ids: list[int]
    other_participants: str
    parent_state: dict[str, Any]
    tool_call_id: str
    # Trusted request envelope captured before entering the child graph.  It
    # is internal state, never a model-visible tool argument.
    runtime_context: dict[str, str]
    source_result: dict[str, Any]
    draft_result: dict[str, Any]
    outcome: dict[str, Any]
