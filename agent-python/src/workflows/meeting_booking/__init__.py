"""Deterministic meeting-room booking workflow."""

from .contracts import (
    MeetingBookingWorkflowInput,
    MeetingBookingWorkflowOutcome,
    MeetingBookingWorkflowStatus,
)
__all__ = [
    "MeetingBookingWorkflowOutcome",
    "MeetingBookingWorkflowStatus",
    "MeetingBookingWorkflowInput",
    "run_meeting_booking_workflow",
]


def __getattr__(name):
    if name == "run_meeting_booking_workflow":
        from .graph import run_meeting_booking_workflow
        return run_meeting_booking_workflow
    raise AttributeError(name)
