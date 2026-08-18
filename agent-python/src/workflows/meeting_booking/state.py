"""State carried by one deterministic meeting-booking graph run."""

from __future__ import annotations

from typing import Any

from typing_extensions import TypedDict


class MeetingBookingWorkflowState(TypedDict, total=False):
    operation: str
    source_booking_id: int | None
    cancel_reason: str
    subject: str
    start_time: str
    end_time: str
    attendee_names: list[str] | None
    room_capacity: int | None
    equipment: list[str] | None
    room_preference: str
    remark: str
    # The parent AgentState is passed for the prepare Tool's authorized
    # current-user-message extraction. It must remain checkpoint-serializable;
    # request-scoped runtime objects belong in runtime_context instead.
    parent_state: dict[str, Any]
    # Trusted identity/turn envelope captured by the parent Agent before the
    # nested graph starts.  LangGraph may provide a partial child Runnable
    # config, so every node must restore this envelope before reading or
    # writing Operation state or calling a Java-facing service.
    runtime_context: dict[str, str]
    tool_call_id: str
    source_result: dict[str, Any]
    prepare_result: dict[str, Any]
    rooms_result: dict[str, Any]
    availability_result: dict[str, Any]
    draft_result: dict[str, Any]
    outcome: dict[str, Any]
