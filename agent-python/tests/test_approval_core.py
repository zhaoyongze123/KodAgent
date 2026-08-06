from src.services.approval_core import (
    ApprovalBinding,
    identity_mismatch,
    resume_runtime,
)


def _binding() -> ApprovalBinding:
    runtime, resume_run_id = resume_runtime(
        {"tenantId": "tenant-1", "userId": "user-1", "threadId": "thread-1", "messageId": "message-1", "runId": "resume-1"},
        "origin-1",
    )
    return ApprovalBinding(
        draft={"draftId": "draft-1", "approvalId": "approval-1"},
        approval={"approvalId": "approval-1"},
        runtime=runtime,
        origin_run_id="origin-1",
        resume_run_id=resume_run_id,
    )


def test_identity_mismatch_reports_the_first_missing_or_wrong_field():
    binding = _binding()

    assert identity_mismatch(binding.draft, binding.runtime) == "tenantId"
    assert identity_mismatch({**binding.runtime}, binding.runtime) is None
