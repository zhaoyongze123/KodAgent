import pytest
from types import SimpleNamespace

from src.domain.effect import EffectRecord, transition_effect
from src.tools.approval import actions, common as approval_common, history, pending, query, templates
from src.tools.common import http_client
from src.services.approval_batch_approval import ApprovalBatchContext, confirmation_args
from src.services.approval_request_approval import ApprovalRequestContext, confirmation_args as request_confirmation_args
from src.services.approval_task_approval import ApprovalTaskContext


def test_approval_request_only_accepts_fixed_oa_types_and_fields():
    payload, failure = query._request_payload(
        "leave", "2026-08-01 09:00:00", "2026-08-01 18:00:00", 1, "家庭事务"
    )

    assert failure is None
    assert payload == {
        "requestType": "leave",
        "startTime": "2026-08-01 09:00:00",
        "endTime": "2026-08-01 18:00:00",
        "type": 1,
        "reason": "家庭事务",
    }

    _, failure = query._request_payload(
        "generic", "2026-08-01 09:00:00", "2026-08-01 18:00:00", 1, "测试"
    )
    assert failure.error.code == "APPROVAL_TYPE_UNSUPPORTED"


def test_approval_paths_are_mapped_to_specific_contracts():
    assert http_client._tool_name_for_path("/agent/tools/approvals/types") == "list_startable_approval_types"
    assert http_client._tool_name_for_path("/agent/tools/approvals/preview", "POST") == "preview_approval_request"
    with pytest.raises(RuntimeError, match="未登记 Java Facade 路径"):
        http_client._tool_name_for_path("/agent/tools/approvals/submit", "POST")
    assert http_client._tool_name_for_path("/agent/tools/approvals/request-draft", "POST") == "create_approval_request_draft"
    assert http_client._tool_name_for_path("/agent/tools/approvals/request-commit", "POST") == "confirm_approval_request_action"
    assert http_client._tool_name_for_path("/agent/tools/approvals/generic/draft", "POST") == "create_generic_approval_request_draft"
    assert http_client._tool_name_for_path("/agent/tools/approvals/generic/commit", "POST") == "confirm_approval_request_action"
    assert http_client._tool_name_for_path("/agent/tools/approvals/withdraw-draft", "POST") == "create_approval_withdraw_draft"
    assert http_client._tool_name_for_path("/agent/tools/approvals/withdraw-commit", "POST") == "confirm_approval_withdraw_action"
    assert http_client._tool_name_for_path("/agent/tools/approvals/inbox") == "search_my_pending_approvals"
    assert http_client._tool_name_for_path("/agent/tools/tasks/todo") == "list_my_pending_approvals"
    assert http_client._tool_name_for_path("/agent/tools/tasks/task-1") == "get_approval_task_detail"
    assert http_client._tool_name_for_path("/agent/tools/tasks/action-preview", "POST") == "preview_approval_task_action"
    assert http_client._tool_name_for_path("/agent/tools/tasks/action-execute", "POST") == "confirm_approval_task_action"
    assert http_client._tool_name_for_path("/agent/tools/tasks/action-reconcile", "POST") == "reconcile_approval_task_action"
    with pytest.raises(RuntimeError, match="未登记 Java Facade 路径"):
        http_client._tool_name_for_path("/agent/tools/tasks/approve", "POST")


def test_inbox_search_forwards_only_structured_read_only_conditions(monkeypatch):
    monkeypatch.setattr(pending, "get_stream_writer", lambda: None)
    captured = {}

    def get(path, params):
        captured["path"] = path
        captured["params"] = params
        return {"candidates": [{"taskId": "task-1"}], "excludedCount": 2}

    monkeypatch.setattr(pending, "java_get", get)
    result = pending.search_my_pending_approvals.func(
        process_types=["报销审批", " "], amount_operator="lte", amount=5000,
        department="研发部", min_pending_days=2, sort_by="amount_desc", page_size=99,
    )

    assert result.ok is True
    assert result.presentation == {"blockType": "card", "cardType": "approval_inbox"}
    assert captured == {
        "path": "/agent/tools/approvals/inbox",
        "params": {
            "processTypes": ["报销审批"], "amountOperator": "LTE", "amount": 5000,
            "department": "研发部", "minPendingDays": 2, "sortBy": "AMOUNT_DESC", "pageSize": 50,
        },
    }


def test_canonical_query_plan_forwards_fixed_sort_and_scope(monkeypatch):
    monkeypatch.setattr(pending, "get_stream_writer", lambda: None)
    captured = {}

    def get(path, params):
        captured["path"] = path
        captured["params"] = params
        return {"candidates": [{"taskId": "task-1", "amount": 900}], "totalPending": 1}

    monkeypatch.setattr(pending, "java_get", get)
    result = pending.run_approval_query_plan.func(
        plan={
            "entity": "pending_approval",
            "operation": "rank",
            "filters": [{"field": "amount", "operator": "NOT_NULL"}],
            "sort": [{"field": "amount", "direction": "DESC"}],
            "limit": 10,
            "null_policy": "EXCLUDE",
            "execution_order": ["filter", "sort", "limit"],
            "requested_scope": {"limit": 10},
            "applied_policies": ["金额排序前排除空金额"],
        }
    )

    assert result.ok is True
    assert captured == {
        "path": "/agent/tools/approvals/inbox",
        "params": {"pageNo": 1, "pageSize": 10, "amountPresent": True, "sortBy": "AMOUNT_DESC"},
    }
    assert result.data["sortApplied"] == "AMOUNT_DESC"
    assert result.data["nullPolicy"] == "EXCLUDE"
    assert result.presentation["resultKind"] == "ranked_list"


def test_canonical_query_plan_enforces_limit_when_facade_overreturns(monkeypatch):
    """The structured result cannot exceed the canonical plan limit."""
    monkeypatch.setattr(pending, "get_stream_writer", lambda: None)
    captured = {}

    def get(path, params):
        captured["path"] = path
        captured["params"] = params
        return {
            "totalPending": 18,
            "matchedCount": 18,
            "candidates": [{"taskId": f"task-{index}"} for index in range(18)],
        }

    monkeypatch.setattr(pending, "java_get", get)
    result = pending.run_approval_query_plan.func(
        plan={
            "entity": "pending_approval",
            "operation": "rank",
            "sort": [{"field": "created_time", "direction": "DESC"}],
            "limit": 3,
            "requested_scope": {"limit": 3},
        }
    )

    assert result.ok is True
    assert captured["params"] == {"pageNo": 1, "pageSize": 3, "sortBy": "CREATED_DESC"}
    assert len(result.data["candidates"]) == 3
    assert result.data["returnedCount"] == 3
    assert result.data["requestedLimit"] == 3
    assert result.data["pageSize"] == 3
    assert result.data["serverReturnedCount"] == 18
    assert result.data["boundedByPlan"] is True


def test_approval_read_adapters_keep_items_within_requested_page_size(monkeypatch):
    monkeypatch.setattr(history, "get_stream_writer", lambda: None)
    monkeypatch.setattr(approval_common, "get_stream_writer", lambda: None)
    monkeypatch.setattr(
        history,
        "java_get",
        lambda _path, _params: {"total": 18, "items": [{"id": index} for index in range(18)]},
    )
    monkeypatch.setattr(
        approval_common,
        "java_get",
        lambda _path, _params: {"total": 18, "items": [{"id": index} for index in range(18)]},
    )

    result = history.list_my_approval_applications.func(page_no=1, page_size=3)

    assert result.ok is True
    assert len(result.data["items"]) == 3
    assert result.data["returnedCount"] == 3
    assert result.data["requestedLimit"] == 3
    assert result.data["serverReturnedCount"] == 18


def test_request_and_withdraw_confirmation_cards_use_distinct_actions():
    request = ApprovalRequestContext(
        approval={
            "approvalId": "approval-request-1", "draftId": "draft-1", "draftType": "APPROVAL_REQUEST",
            "status": "PENDING", "expiresAt": "2026-08-02T12:15:00",
            "draft": {"requestType": "leave", "startTime": "2026-08-01 09:00:00", "endTime": "2026-08-01 18:00:00", "reason": "家庭事务", "preview": {"normalizedSummary": "部门负责人"}},
        },
        runtime={"threadId": "thread-1", "runId": "run-1", "messageId": "message-1"},
    )
    withdraw = ApprovalRequestContext(
        approval={
            "approvalId": "approval-withdraw-1", "draftId": "draft-2", "draftType": "APPROVAL_WITHDRAW",
            "status": "PENDING", "expiresAt": "2026-08-02T12:15:00",
            "draft": {"processInstanceId": "process-1", "reason": "信息填写错误"},
        },
        runtime={"threadId": "thread-1", "runId": "run-1", "messageId": "message-2"},
    )

    request_card = request_confirmation_args(request, {})
    withdraw_card = request_confirmation_args(withdraw, {})

    assert request_card["action"] == "confirm_approval_request_action"
    assert request_card["cardType"] == "approval_request"
    assert withdraw_card["action"] == "confirm_approval_withdraw_action"
    assert withdraw_card["cardType"] == "approval_request"
    assert withdraw_card["fields"][1] == {"label": "撤回原因", "value": "信息填写错误"}


def test_preview_uses_only_known_fields(monkeypatch):
    monkeypatch.setattr(templates, "get_stream_writer", lambda: None)
    captured = {}

    def post(path, payload):
        captured["path"] = path
        captured["payload"] = payload
        return {"normalizedSummary": "部门负责人"}

    monkeypatch.setattr(templates, "java_post", post)
    result = templates.preview_approval_request.func(
        request_type="trip",
        start_time="2026-08-01 09:00:00",
        end_time="2026-08-02 18:00:00",
        approval_type=2,
        reason="客户拜访",
    )

    assert result.ok is True
    assert captured == {
        "path": "/agent/tools/approvals/preview",
        "payload": {
            "requestType": "trip",
            "startTime": "2026-08-01 09:00:00",
            "endTime": "2026-08-02 18:00:00",
            "type": 2,
            "reason": "客户拜访",
        },
    }


def _batch_context(status: str = "APPROVED") -> ApprovalBatchContext:
    return ApprovalBatchContext(
        preview={
            "previewId": "preview-1",
            "confirmationToken": "token-1",
            "operationId": "op-batch-1",
            "status": status,
            "expiresAt": "2026-08-02T12:15:00",
            "preview": {
                "action": "REJECT",
                "reason": "材料不完整",
                "tasks": [{"taskId": "task-1", "name": "报销审批"}],
            },
        },
        runtime={"threadId": "thread-1", "messageId": "message-1", "operationId": "op-batch-1"},
        origin_run_id="run-1",
    )


class _BatchCommitRuntime:
    """In-memory Operation/Effect boundary for approval action unit tests."""

    def __init__(self):
        self.operation_id = "op-batch-1"
        self.operation = SimpleNamespace(
            action_id="approval.write.batch", status="WAITING_APPROVAL", result={}
        )
        self.effect = None
        self.closed = False

    def close(self):
        self.closed = True

    def get_effect(self, idempotency_key):
        return self.effect if self.effect and self.effect.idempotency_key == idempotency_key else None

    def create_effect(self, *, request_data, reconcile_strategy, idempotency_key):
        self.effect = EffectRecord(
            operation_id=self.operation_id,
            action_id=self.operation.action_id,
            idempotency_key=idempotency_key,
            request_hash="batch-request-hash",
            reconcile_strategy=reconcile_strategy,
            request_data=request_data,
        )
        return self.effect

    def claim_effect(self, effect, *, lease_owner, lease_until):
        self.effect = transition_effect(effect, "CLAIMED").model_copy(update={
            "attempt": effect.attempt + 1,
            "lease_owner": lease_owner,
            "lease_until": lease_until,
        })
        return self.effect

    def transition_effect(self, effect, status, *, response_data=None, error_data=None):
        updated = transition_effect(effect, status)
        updates = {}
        if response_data is not None:
            updates["response_data"] = response_data
        if error_data is not None:
            updates["error_data"] = error_data
        self.effect = updated.model_copy(update=updates)
        return self.effect

    def transition(self, status, *, event_type=None, data=None):
        del event_type, data
        self.operation.status = status
        return self.operation

    def patch_result(self, result, *, event_type="operation.result.updated"):
        del event_type
        self.operation.result = dict(result)
        return self.operation


def _patch_batch_runtime(monkeypatch):
    runtime = _BatchCommitRuntime()
    monkeypatch.setattr(
        actions.OperationRuntime,
        "open_existing",
        classmethod(lambda cls, operation_id, *, required=None: runtime),
    )
    monkeypatch.setattr(
        actions.OperationRuntime,
        "settle_approval",
        classmethod(lambda cls, *args, **kwargs: None),
    )
    return runtime


def test_batch_confirmation_card_is_bound_to_preview_and_expiry():
    args = confirmation_args(_batch_context("PENDING"), {})

    assert args["action"] == "confirm_approval_batch_action"
    assert args["cardType"] == "approval_batch"
    assert args["approvalId"] == "preview-1"
    assert args["draftId"] == "preview-1"
    assert args["expiresAt"] == "2026-08-02T12:15:00"
    assert args["approveLabel"] == "确认批量驳回"
    assert args["rejectLabel"] == "取消操作"


def test_batch_confirmation_cannot_execute_from_text_or_pending_context(monkeypatch):
    context = _batch_context("PENDING")
    monkeypatch.setattr(actions, "load_approval_batch", lambda *_: (context, None))
    monkeypatch.setattr(actions, "can_execute_batch", lambda _: False)
    monkeypatch.setattr(actions, "can_replay_batch", lambda _: False)
    monkeypatch.setattr(actions, "java_post", lambda *_: (_ for _ in ()).throw(AssertionError("must not execute")))

    result = actions.confirm_approval_batch_action.func("preview-1", "token-1")

    assert result.ok is False
    assert result.error.code == "APPROVAL_RESUME_REQUIRED"


def test_batch_confirmation_executes_only_after_official_resume(monkeypatch):
    context = _batch_context("APPROVED")
    _patch_batch_runtime(monkeypatch)
    captured = {}
    completed = []
    monkeypatch.setattr(actions, "get_stream_writer", lambda: None)
    monkeypatch.setattr(actions, "load_approval_batch", lambda *_: (context, None))
    monkeypatch.setattr(actions, "can_execute_batch", lambda _: True)
    monkeypatch.setattr(actions, "can_replay_batch", lambda _: False)
    monkeypatch.setattr(actions, "complete_batch", lambda value: completed.append(value))
    monkeypatch.setattr(actions, "java_post", lambda path, payload: captured.update(path=path, payload=payload) or {
        "previewId": "preview-1", "results": [{"taskId": "task-1", "status": "SUCCESS"}],
    })

    result = actions.confirm_approval_batch_action.func("preview-1", "token-1")

    assert result.ok is True
    assert completed == [context]
    assert captured == {
        "path": "/agent/tools/approvals/batch/execute",
        "payload": {
            "previewId": "preview-1",
            "confirmationToken": "token-1",
            "confirmationMessageId": "message-1",
            "operationId": "op-batch-1",
            "idempotencyKey": "approval-batch:v2:preview-1",
        },
    }


def test_batch_rejection_is_a_terminal_resume_not_an_execution_failure(monkeypatch):
    context = _batch_context("REJECTED")
    _patch_batch_runtime(monkeypatch)
    completed = []
    monkeypatch.setattr(actions, "get_stream_writer", lambda: None)
    monkeypatch.setattr(actions, "load_approval_batch", lambda *_: (context, None))
    monkeypatch.setattr(actions, "complete_batch", lambda value: completed.append(value))
    monkeypatch.setattr(actions, "java_post", lambda *_: (_ for _ in ()).throw(AssertionError("must not execute")))

    result = actions.confirm_approval_batch_action.func("preview-1", "token-1")

    assert result.ok is True
    assert result.data == {"previewId": "preview-1", "status": "REJECTED", "cancelled": True}
    assert completed == [context]


def test_completed_batch_resume_replays_java_result_without_a_second_mutation(monkeypatch):
    context = _batch_context("COMPLETED")
    _patch_batch_runtime(monkeypatch)
    captured = {}
    monkeypatch.setattr(actions, "get_stream_writer", lambda: None)
    monkeypatch.setattr(actions, "load_approval_batch", lambda *_: (context, None))
    monkeypatch.setattr(actions, "can_execute_batch", lambda _: False)
    monkeypatch.setattr(actions, "can_replay_batch", lambda _: True)
    monkeypatch.setattr(actions, "complete_batch", lambda _: None)
    monkeypatch.setattr(actions, "java_post", lambda path, payload: captured.update(path=path, payload=payload) or {
        "previewId": "preview-1", "idempotentReplay": True, "results": []
    })

    result = actions.confirm_approval_batch_action.func("preview-1", "token-1")

    assert result.ok is True
    assert result.data["idempotentReplay"] is True
    assert captured["payload"]["idempotencyKey"] == "approval-batch:v2:preview-1"


def test_completed_task_resume_replays_effect_without_a_second_mutation(monkeypatch):
    context = ApprovalTaskContext(
        approval={
            "approvalId": "approval-task-1",
            "draftId": "draft-task-1",
            "draftType": "APPROVAL_TASK",
            "operationId": "op-task-1",
            "status": "COMPLETED",
            "draft": {"taskId": "task-1", "action": "APPROVE", "result": {
                "success": True, "taskId": "task-1", "action": "APPROVE",
            }},
        },
        runtime={"runId": "resume-1", "threadId": "thread-1", "messageId": "message-1"},
    )

    class Runtime:
        operation_id = "op-task-1"

        def get_effect(self, _key):
            return SimpleNamespace(
                status="SUCCEEDED",
                response_data={"success": True, "taskId": "task-1", "action": "APPROVE"},
            )

        def close(self):
            pass

    monkeypatch.setattr(actions, "get_stream_writer", lambda: None)
    monkeypatch.setattr(actions, "load_approval_task_context", lambda *_: (context, None))
    monkeypatch.setattr(actions.OperationRuntime, "open_existing", lambda *_args, **_kwargs: Runtime())
    monkeypatch.setattr(actions, "java_post", lambda *_: (_ for _ in ()).throw(AssertionError("must not mutate BPM")))

    result = actions.confirm_approval_task_action.func("approval-task-1", "tool-1")

    assert result.ok is True
    assert result.data == {"success": True, "taskId": "task-1", "action": "APPROVE"}


def test_submitting_task_resume_only_reconciles_existing_effect(monkeypatch):
    context = ApprovalTaskContext(
        approval={
            "approvalId": "approval-task-2",
            "draftId": "draft-task-2",
            "draftType": "APPROVAL_TASK",
            "operationId": "op-task-2",
            "status": "SUBMITTING",
            "draft": {"taskId": "task-2", "action": "APPROVE", "reason": "同意"},
        },
        runtime={"runId": "resume-2", "threadId": "thread-2", "messageId": "message-2"},
    )

    class Runtime:
        operation_id = "op-task-2"

        def get_effect(self, _key):
            return SimpleNamespace(status="UNKNOWN")

        def close(self):
            pass

    class Coordinator:
        effect = SimpleNamespace(status="UNKNOWN")

        def prepare(self):
            return SimpleNamespace(
                effect=self.effect,
                reconciliation_required=True,
                recovered_result=None,
            )

    monkeypatch.setattr(actions, "get_stream_writer", lambda: None)
    monkeypatch.setattr(actions, "load_approval_task_context", lambda *_: (context, None))
    monkeypatch.setattr(actions.OperationRuntime, "open_existing", lambda *_args, **_kwargs: Runtime())
    monkeypatch.setattr(actions, "_task_commit_coordinator", lambda *_args, **_kwargs: Coordinator())
    monkeypatch.setattr(actions, "_reconcile_task_effect", lambda *_args: {
        "success": True, "taskId": "task-2", "action": "APPROVE",
    })
    monkeypatch.setattr(actions, "complete_task", lambda _context: None)
    monkeypatch.setattr(actions, "java_post", lambda *_: (_ for _ in ()).throw(AssertionError("must not retry BPM")))

    result = actions.confirm_approval_task_action.func("approval-task-2", "tool-2")

    assert result.ok is True
    assert result.data == {"success": True, "taskId": "task-2", "action": "APPROVE"}
