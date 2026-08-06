from __future__ import annotations

import pytest

from src.domain.operation import (
    OperationContext,
    OperationTransitionError,
    bind_approval,
    transition_operation,
)


def _operation(*, status: str = "RUNNING", approval_id: str | None = None) -> OperationContext:
    return OperationContext(
        operation_id="op-approval-1",
        action_id="meeting.create",
        capability_id="meeting",
        tenant_id="tenant-1",
        user_id="user-1",
        thread_id="thread-1",
        origin_run_id="run-1",
        current_run_id="run-1",
        message_id="message-1",
        status=status,
        approval_id=approval_id,
    )


def test_approval_binding_is_metadata_and_does_not_fake_a_status_transition():
    operation = _operation()
    bound = bind_approval(operation, "approval-1", expected_version=1)

    assert bound.approval_id == "approval-1"
    assert bound.status == "RUNNING"
    assert bound.version == 2


def test_waiting_approval_has_one_explicit_commit_transition():
    waiting = _operation(status="WAITING_APPROVAL", approval_id="approval-1")
    committing = transition_operation(waiting, "COMMITTING", expected_version=1)

    assert committing.status == "COMMITTING"
    assert committing.version == 2


def test_terminal_operation_cannot_be_reopened_by_a_resume():
    succeeded = _operation(status="SUCCEEDED", approval_id="approval-1")

    with pytest.raises(OperationTransitionError):
        transition_operation(succeeded, "RUNNING", expected_version=1)
