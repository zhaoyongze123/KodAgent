from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.domain.operation import (
    OperationContext,
    OperationTransitionError,
    patch_operation,
    transition_operation,
)


def _operation(operation_id: str = "op-1", *, status: str = "CREATED") -> OperationContext:
    return OperationContext(
        operation_id=operation_id,
        action_id="meeting.create",
        capability_id="meeting",
        tenant_id="tenant-1",
        user_id="user-1",
        thread_id="thread-1",
        origin_run_id="run-1",
        current_run_id="run-1",
        message_id="message-1",
        status=status,
    )


def test_operation_is_the_durable_unit_and_payload_updates_are_versioned():
    operation = _operation()
    collecting = transition_operation(operation, "COLLECTING_INFO", expected_version=1)
    ready = transition_operation(collecting, "READY", expected_version=2)
    patched = patch_operation(
        ready,
        expected_version=ready.version,
        payload={"meeting_request": {"subject": "项目评审"}},
    )

    assert patched.operation_id == operation.operation_id
    assert patched.status == "READY"
    assert patched.version == ready.version + 1
    assert patched.payload["meeting_request"]["subject"] == "项目评审"


def test_one_thread_can_have_independent_operations_without_an_active_slot():
    meeting = _operation("op-meeting").model_copy(update={"payload": {"sourceBookingId": 40}})
    schedule = _operation("op-schedule").model_copy(update={
        "action_id": "schedule.create",
        "capability_id": "schedule",
        "payload": {"title": "个人日程"},
    })

    assert meeting.thread_id == schedule.thread_id
    assert meeting.operation_id != schedule.operation_id
    assert meeting.payload != schedule.payload


def test_operation_does_not_accept_removed_task_fields():
    with pytest.raises(ValidationError):
        OperationContext(
            **_operation().model_dump(),
            task_type="meeting_booking",
        )


def test_stale_operation_revision_cannot_patch_payload():
    with pytest.raises(OperationTransitionError, match="version conflict"):
        patch_operation(_operation(), expected_version=2, payload={"x": 1})
