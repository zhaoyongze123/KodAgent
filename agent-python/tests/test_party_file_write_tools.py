import pytest
from types import SimpleNamespace

from src.tools.common import JavaFacadeBusinessError
from src.tools.party_files import manage


def _install_draft_mocks(monkeypatch, calls):
    monkeypatch.setattr(
        manage,
        "current_agent_context",
        lambda: {"runId": "run-1", "threadId": "thread-1", "messageId": "message-1", "userId": "1", "tenantId": "1"},
    )
    monkeypatch.setattr(manage, "get_stream_writer", lambda: object())
    monkeypatch.setattr(manage, "emit", lambda *args, **kwargs: None)

    class FakeOperationRuntime:
        operation_id = "op-party-file-test"

        def __init__(self):
            self.operation = SimpleNamespace(status="COLLECTING_INFO")

        def transition(self, status, **kwargs):
            self.operation.status = status
            return self.operation

        def bind_approval(self, approval_id):
            self.operation.approval_id = approval_id
            return self.operation

        def close(self):
            return None

    monkeypatch.setattr(manage.OperationRuntime, "start", lambda **kwargs: FakeOperationRuntime())

    def java_post(path, payload):
        calls.append((path, payload))
        return {"draftId": "draft-1", "approvalId": "approval-1", "draft": payload}

    monkeypatch.setattr(manage, "java_post", java_post)


def test_create_party_file_resolves_category_name_with_list_contract(monkeypatch):
    calls = []
    _install_draft_mocks(monkeypatch, calls)
    monkeypatch.setattr(
        manage,
        "java_get_list",
        lambda path: [{"id": 7, "name": "联调党务分类"}],
    )

    result = manage.create_party_file_draft.func(
        title="自然语言创建验收",
        category_name="联调党务分类",
        distribute_to_self=True,
        content="正文",
        tool_call_id="call-create",
    )

    assert result.ok is True
    assert calls[0][0] == "/agent/tools/party-files/drafts/create"
    assert calls[0][1]["categoryId"] == 7
    assert calls[0][1]["targets"] == [{"targetType": 2, "targetId": 1}]
    assert "taskId" not in calls[0][1]
    assert "task_id" not in calls[0][1]


def test_create_party_file_normalizes_short_notice_category_alias(monkeypatch):
    calls = []
    _install_draft_mocks(monkeypatch, calls)
    seen = []

    def java_get_list(path):
        seen.append(path)
        return [{"id": 5, "name": "通知公告"}]

    monkeypatch.setattr(manage, "java_get_list", java_get_list)
    result = manage.create_party_file_draft.func(
        title="关于党员活动的通知",
        category_name="通知",
        content="正文",
        tool_call_id="call-short-category",
    )

    assert result.ok is True
    assert seen == ["/agent/tools/party-files/categories"]
    assert calls[0][1]["categoryId"] == 5


def test_create_party_file_infers_notice_category_and_defaults_publish_time_and_audience(monkeypatch):
    calls = []
    _install_draft_mocks(monkeypatch, calls)
    category_calls = []

    def java_get_list(path):
        category_calls.append(path)
        return [{"id": 5, "name": "通知公告"}]

    monkeypatch.setattr(manage, "java_get_list", java_get_list)

    result = manage.create_party_file_draft.func(
        title="关于组织开展党员志愿服务周活动的通知",
        content="正文",
        tool_call_id="call-infer-notice",
    )

    assert result.ok is True
    assert category_calls == ["/agent/tools/party-files/categories"]
    payload = calls[0][1]
    assert payload["categoryId"] == 5
    assert payload["publishTime"]
    assert payload["targets"] == [{"targetType": 1}]


def test_create_party_file_unknown_category_fails_before_java_draft_post(monkeypatch):
    calls = []
    _install_draft_mocks(monkeypatch, calls)
    monkeypatch.setattr(manage, "java_get_list", lambda path: [])

    result = manage.create_party_file_draft.func(
        title="季度工作记录",
        content="正文",
        tool_call_id="call-unknown-category",
    )

    assert result.ok is False
    assert result.error.code == "PARTY_FILE_CATEGORY_REQUIRED"
    assert calls == []


def test_create_party_file_unknown_explicit_category_uses_stable_category_error(monkeypatch):
    calls = []
    _install_draft_mocks(monkeypatch, calls)
    monkeypatch.setattr(manage, "java_get_list", lambda path: [{"id": 5, "name": "通知公告"}])

    result = manage.create_party_file_draft.func(
        title="通知",
        category_name="不存在的分类",
        content="正文",
        tool_call_id="call-unknown-explicit-category",
    )

    assert result.ok is False
    assert result.error.code == "PARTY_FILE_CATEGORY_REQUIRED"
    assert calls == []


def test_create_party_file_maps_java_required_category_error(monkeypatch):
    calls = []
    _install_draft_mocks(monkeypatch, calls)

    def java_post(path, payload):
        raise JavaFacadeBusinessError(400, "缺少 categoryId", {"code": 400, "msg": "缺少 categoryId"}, path)

    monkeypatch.setattr(manage, "java_post", java_post)
    result = manage.create_party_file_draft.func(
        title="通知",
        category_id=5,
        content="正文",
        tool_call_id="call-java-category-error",
    )

    assert result.ok is False
    assert result.error.code == "PARTY_FILE_CATEGORY_REQUIRED"
    assert "文件类别" in result.error.message


@pytest.mark.parametrize(
    ("java_message", "expected_code"),
    [
        ("缺少 publishTime", "PARTY_FILE_PUBLISH_TIME_REQUIRED"),
        ("党务文件必须指定分发对象", "PARTY_FILE_TARGET_REQUIRED"),
        ("无权执行党务文件CREATE操作", "PARTY_FILE_PERMISSION_DENIED"),
    ],
)
def test_create_party_file_maps_java_validation_errors(monkeypatch, java_message, expected_code):
    calls = []
    _install_draft_mocks(monkeypatch, calls)

    def java_post(path, payload):
        raise JavaFacadeBusinessError(400, java_message, {"code": 400, "msg": java_message}, path)

    monkeypatch.setattr(manage, "java_post", java_post)
    result = manage.create_party_file_draft.func(
        title="通知",
        category_id=5,
        content="正文",
        tool_call_id="call-java-validation-error",
    )

    assert result.ok is False
    assert result.error.code == expected_code


def test_create_tool_rejects_update_and_delete_operations(monkeypatch):
    result = manage.create_party_file_draft.func(operation="UPDATE", tool_call_id="call-1")
    assert result.ok is False
    assert result.error.code == "PARTY_FILE_TOOL_BOUNDARY"


def test_update_party_file_draft_uses_update_route(monkeypatch):
    calls = []
    _install_draft_mocks(monkeypatch, calls)

    result = manage.update_party_file_draft.func(
        source_party_file_id=42, title="", category_id=None, tool_call_id="call-update"
    )

    assert result.ok is True
    assert calls[0][0] == "/agent/tools/party-files/drafts/update"
    assert calls[0][1]["operation"] == "UPDATE"
    assert calls[0][1]["sourcePartyFileId"] == 42
    assert calls[0][1]["targets"] == []


def test_delete_party_file_draft_uses_delete_route(monkeypatch):
    calls = []
    _install_draft_mocks(monkeypatch, calls)

    result = manage.delete_party_file_draft.func(source_party_file_id=42, tool_call_id="call-delete")

    assert result.ok is True
    assert calls[0][0] == "/agent/tools/party-files/drafts/delete"
    assert calls[0][1]["operation"] == "DELETE"
    assert calls[0][1]["sourcePartyFileId"] == 42
