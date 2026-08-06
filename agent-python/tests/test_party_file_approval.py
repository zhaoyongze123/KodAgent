import json
from types import SimpleNamespace

from langchain.agents.middleware.types import ModelResponse
from langchain_core.messages import AIMessage, ToolMessage

from src.services import party_file_approval
from src.tools.party_files import manage


def _request(messages, tool_call=None):
    return SimpleNamespace(state={"messages": messages}, tool_call=tool_call)


def test_party_file_update_draft_projects_operation_specific_confirmation(monkeypatch):
    monkeypatch.setattr(
        party_file_approval,
        "current_agent_context",
        lambda: {"runId": "run-1", "threadId": "thread-1", "messageId": "msg-1"},
    )
    draft = {
        "operation": "UPDATE",
        "sourcePartyFileId": 42,
        "title": "制度修订版",
        "categoryId": 3,
        "status": 0,
        "targets": [{"targetType": 1}],
    }
    tool_result = {"ok": True, "data": {"draftId": "draft-1", "approvalId": "approval-1", "draft": draft}}
    request = _request([
        ToolMessage(
            name="update_party_file_draft",
            tool_call_id="call-1",
            content=json.dumps(tool_result, ensure_ascii=False),
        )
    ])
    response = ModelResponse(result=[AIMessage(content="等待确认")])

    result = party_file_approval.PartyFileApprovalAutoConfirmMiddleware().wrap_model_call(
        request, lambda _: response
    )
    call = result.result[0].tool_calls[0]
    assert call["name"] == "confirm_update_party_file"
    assert call["args"]["draftId"] == "draft-1"
    assert call["args"]["cardType"] == "party_file_approval"
    assert call["args"]["fields"][0] == {"label": "操作", "value": "更新党务文件"}
    assert result.result[0].additional_kwargs[party_file_approval.PROJECTION_METADATA_KEY]["action"] == "confirm_update_party_file"


def test_party_file_confirmation_fields_use_human_labels_not_internal_codes():
    fields = party_file_approval._fields({
        "operation": "CREATE",
        "title": "验收通知",
        "categoryId": 5,
        "status": 0,
        "presentation": {
            "categoryName": "通知公告",
            "statusLabel": "已发布",
            "storageTypeLabel": "本地存储",
            "distributionLabel": "全员",
            "attachmentLabel": "无附件",
            "publishTime": "2026-08-04 13:31:22",
        },
    })
    assert {field["label"]: field["value"] for field in fields} == {
        "操作": "发布党务文件",
        "标题": "验收通知",
        "分类": "通知公告",
        "发布时间": "2026-08-04 13:31:22",
        "状态": "已发布",
        "存储方式": "本地存储",
        "分发对象": "全员",
        "附件": "无附件",
    }
    assert all("categoryId" not in field["value"] for field in fields)


def test_party_file_delete_draft_projects_delete_confirmation(monkeypatch):
    monkeypatch.setattr(party_file_approval, "current_agent_context", lambda: {"runId": "run-1", "threadId": "thread-1", "messageId": "msg-1"})
    draft = {"operation": "DELETE", "sourcePartyFileId": 42}
    result = party_file_approval.PartyFileApprovalAutoConfirmMiddleware().wrap_model_call(
        _request([ToolMessage(name="delete_party_file_draft", tool_call_id="call-1", content=json.dumps({"ok": True, "data": {"draftId": "draft-delete", "approvalId": "approval-delete", "draft": draft}}))]),
        lambda _: ModelResponse(result=[AIMessage(content="等待确认")]),
    )
    call = result.result[0].tool_calls[0]
    assert call["name"] == "confirm_delete_party_file"
    assert call["args"]["draftId"] == "draft-delete"
    assert call["args"]["cardType"] == "party_file_approval"
    assert result.result[0].additional_kwargs[party_file_approval.PROJECTION_METADATA_KEY] == party_file_approval.approval_projection_metadata(
        action="confirm_delete_party_file", approval_id="approval-delete", draft_id="draft-delete", origin_run_id="run-1", message_id="msg-1"
    )


def test_party_file_confirmation_interrupt_requires_trusted_pending_approval(monkeypatch):
    monkeypatch.setattr(
        party_file_approval,
        "current_agent_context",
        lambda: {
            "runId": "run-1", "originRunId": "run-1", "threadId": "thread-1",
            "messageId": "msg-1", "tenantId": "1", "userId": "1",
        },
    )
    draft = {
        "draftId": "draft-1", "approvalId": "approval-1", "operation": "CREATE",
        "operationId": "op-party-file-1", "runId": "run-1", "threadId": "thread-1",
        "messageId": "msg-1", "tenantId": "1", "userId": "1",
    }
    approval = {
        "approvalId": "approval-1", "draftId": "draft-1", "draftType": "PARTY_FILE",
        "status": "PENDING", "operationId": "op-party-file-1", "runId": "run-1",
        "threadId": "thread-1", "messageId": "msg-1", "tenantId": "1", "userId": "1",
    }
    monkeypatch.setattr(
        party_file_approval,
        "java_get",
        lambda path: approval if path == "/agent/approvals/approval-1" else {"draft": draft},
    )

    class FakeRuntime:
        operation = type("Operation", (), {"action_id": "party_file.create", "status": "WAITING_APPROVAL"})()

        def close(self):
            return None

    monkeypatch.setattr(party_file_approval.OperationRuntime, "open_existing", lambda *args, **kwargs: FakeRuntime())
    monkeypatch.setattr(party_file_approval, "emit", lambda *args, **kwargs: None)
    action = {
        "name": "confirm_create_party_file",
        "id": "call-1",
        "args": {"approvalId": "approval-1", "draftId": "draft-1"},
    }
    proof = party_file_approval.approval_projection_metadata(
        action="confirm_create_party_file",
        approval_id="approval-1",
        draft_id="draft-1",
        origin_run_id="run-1",
        message_id="msg-1",
    )
    message = AIMessage(
        content="",
        tool_calls=[{**action, "id": "call-1", "type": "tool_call"}],
        additional_kwargs={party_file_approval.PROJECTION_METADATA_KEY: proof},
    )
    request = _request([message], tool_call=action)
    assert party_file_approval.prepare_party_file_confirmation(request) is True


def test_completed_party_file_resume_replays_effect_without_second_approval(monkeypatch):
    context = party_file_approval.PartyFileApprovalContext(
        draft={
            "draftId": "draft-1",
            "approvalId": "approval-1",
            "operation": "CREATE",
            "operationId": "operation-1",
        },
        approval={
            "approvalId": "approval-1",
            "status": "COMPLETED",
            "draftType": "PARTY_FILE",
            "operationId": "operation-1",
        },
        runtime={"runId": "run-2", "threadId": "thread-1", "messageId": "msg-1"},
        origin_run_id="run-1",
        resume_run_id="run-2",
    )

    monkeypatch.setattr(
        party_file_approval,
        "load_party_file_confirmation",
        lambda draft_id, approval_id: (context, None),
    )
    monkeypatch.setattr(
        party_file_approval,
        "consume_party_file_resume",
        lambda _: (_ for _ in ()).throw(AssertionError("completed Approval must not consume a second resume")),
    )
    monkeypatch.setattr(manage, "current_agent_context", lambda: {"runId": "run-2"})
    monkeypatch.setattr(manage, "mark_run_resumed", lambda: None)
    monkeypatch.setattr(manage, "get_stream_writer", lambda: None)
    monkeypatch.setattr(manage, "emit", lambda *args, **kwargs: None)

    runtime = SimpleNamespace(
        operation=SimpleNamespace(action_id="party_file.create"),
        close=lambda: None,
    )
    monkeypatch.setattr(manage.OperationRuntime, "open_existing", lambda *args, **kwargs: runtime)

    class FakeCoordinator:
        def __init__(self, **kwargs):
            pass

        def prepare(self):
            return SimpleNamespace(
                reconciliation_required=False,
                recovered_result={"success": True, "fileId": 8001},
            )

    monkeypatch.setattr(manage, "EffectCommitCoordinator", FakeCoordinator)

    result = manage._confirm("CREATE", "draft-1", "draft-1", "approval-1", "call-1")

    assert result.ok is True
    assert result.data == {"success": True, "fileId": 8001}


def test_party_file_reconcile_repairs_java_markers_after_mysql_success(monkeypatch):
    calls = []
    effect = SimpleNamespace(request_data={
        "draftId": "draft-delete",
        "approvalId": "approval-delete",
        "operationId": "operation-delete",
        "operation": "DELETE",
    })
    monkeypatch.setattr(
        manage,
        "get_party_file_commit_status",
        lambda draft_id, approval_id, operation_id: {
            "status": "SUBMITTED",
            "result": {"success": True, "fileId": 19, "operation": "DELETE"},
        },
    )
    monkeypatch.setattr(
        manage,
        "java_post",
        lambda path, payload: calls.append((path, payload)) or {
            "success": True, "fileId": 19, "operation": "DELETE",
        },
    )

    result = manage._resolved_party_file_result(
        effect,
        draft_id="draft-delete",
        approval_id="approval-delete",
        operation_id="operation-delete",
    )

    assert result == {"success": True, "fileId": 19, "operation": "DELETE"}
    assert calls == [(
        "/agent/tools/party-files/commit/delete",
        {
            "draftId": "draft-delete",
            "approvalId": "approval-delete",
            "operationId": "operation-delete",
        },
    )]
