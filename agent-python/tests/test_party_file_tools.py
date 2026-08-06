import pytest

from src.tools.common import http_client
from src.tools.party_files import query


def test_party_file_tool_paths_resolve_to_real_employee_endpoints():
    assert http_client._tool_name_for_path(
        "/agent/tools/party-files/query-plan", "POST"
    ) == "execute_party_file_metadata_plan"
    assert http_client._tool_name_for_path("/agent/tools/party-files/my-page") == "search_party_files"
    assert http_client._tool_name_for_path("/agent/tools/party-files/my-get") == "get_party_file_detail"
    assert (
        http_client._tool_name_for_path("/agent/tools/party-files/my-attachment")
        == "get_party_file_attachment"
    )
    assert (
        http_client._tool_name_for_path("/agent/tools/party-files/drafts/draft-1")
        == "get_party_file_draft"
    )
    assert http_client._tool_name_for_path(
        "/agent/tools/party-files/commit/status"
    ) == "get_party_file_commit_status"


def test_party_file_commit_status_has_a_read_only_retry_contract():
    contract = http_client.get_tool_contract("get_party_file_commit_status")

    assert contract.read_only is True
    assert contract.permission == "party-file:read"
    assert contract.retryable is True
    assert contract.max_retries == 2


def test_party_file_tool_paths_do_not_allow_legacy_or_admin_like_paths():
    for path in (
        "/agent/tools/party-files/search",
        "/agent/tools/party-files/detail",
        "/agent/tools/party-files/attachment",
        "/system/party-file/my-get",
    ):
        try:
            http_client._tool_name_for_path(path)
        except RuntimeError:
            continue
        raise AssertionError(f"legacy or non-Agent path was accepted: {path}")


def test_party_file_generic_draft_path_cannot_use_create_permission_for_other_operations():
    """Only operation-specific draft paths are callable by the facade.

    A generic draft endpoint would be mapped to `party-file:create` before the
    request body is inspected, which could wrongly authorize UPDATE or DELETE.
    """
    with pytest.raises(RuntimeError, match="未登记 Java Facade 路径"):
        http_client._tool_name_for_path("/agent/tools/party-files/drafts", "POST")
    with pytest.raises(RuntimeError, match="未登记 Java Facade 路径"):
        http_client._tool_name_for_path("/agent/tools/party-files/commit", "POST")


def test_detail_contract_excludes_storage_url_and_audience_data():
    detail = query._safe_detail(
        {
            "id": 8,
            "title": "组织生活通知",
            "content": "<p>请参会</p>",
            "summary": "会议通知",
            "attachmentFileIds": "51",
            "kodSourceId": 3,
            "targets": [{"targetName": "全员"}],
            "readList": [{"userNickname": "张三"}],
            "attachments": [
                {
                    "id": 51,
                    "name": "通知.pdf",
                    "url": "kod://private-token-path",
                    "type": "application/pdf",
                    "size": 2048,
                }
            ],
        }
    )

    assert detail == {
        "id": 8,
        "title": "组织生活通知",
        "content": "<p>请参会</p>",
        "summary": "会议通知",
        "attachments": [
            {"id": 51, "name": "通知.pdf", "type": "application/pdf", "size": 2048}
        ],
    }
    assert "url" not in str(detail)
    assert "targets" not in detail
    assert "readList" not in detail


def test_detail_tool_emits_card_with_sanitized_data(monkeypatch):
    emitted = []
    monkeypatch.setattr(query, "get_stream_writer", lambda: object())
    monkeypatch.setattr(query, "emit", lambda *args, **kwargs: emitted.append((args, kwargs)))
    monkeypatch.setattr(
        query,
        "java_get",
        lambda path, params: {
            "id": params["id"],
            "title": "组织生活通知",
            "content": "正文",
            "attachments": [{"id": 51, "name": "通知.pdf", "url": "https://storage/private"}],
            "targets": [{"targetName": "全员"}],
        },
    )

    result = query.get_party_file_detail.func(file_id=8, tool_call_id="call-8")

    assert result.ok is True
    assert result.presentation == {"blockType": "card", "cardType": "party_file", "view": "detail"}
    assert result.data["attachments"] == [{"id": 51, "name": "通知.pdf"}]
    assert "targets" not in result.data
    assert "url" not in str(result.data)
    assert emitted[-1][1]["presentation"]["view"] == "detail"


def test_attachment_query_returns_explicit_no_attachment_result(monkeypatch):
    emitted = []
    monkeypatch.setattr(query, "get_stream_writer", lambda: object())
    monkeypatch.setattr(query, "emit", lambda *args, **kwargs: emitted.append((args, kwargs)))
    monkeypatch.setattr(
        query,
        "java_get",
        lambda path, params: {
            "id": params["id"],
            "title": "无附件通知",
            "attachments": [],
        },
    )

    result = query.get_party_file_attachments.func(file_id=8, tool_call_id="call-attachments")

    assert result.ok is True
    assert result.data["attachmentStatus"] == "NONE"
    assert result.data["attachmentCount"] == 0
    assert result.data["attachmentMessage"] == "该文件没有附件。"
    assert result.presentation == {"blockType": "card", "cardType": "party_file", "view": "attachments"}
    assert emitted[-1][1]["toolName"] == "get_party_file_attachments"


def test_attachment_query_returns_sanitized_attachment_metadata(monkeypatch):
    monkeypatch.setattr(query, "get_stream_writer", lambda: object())
    monkeypatch.setattr(query, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        query,
        "java_get",
        lambda path, params: {
            "id": params["id"],
            "title": "活动通知",
            "attachments": [{"id": 51, "name": "活动方案.pdf", "type": "application/pdf", "size": 2048, "url": "secret"}],
        },
    )

    result = query.get_party_file_attachments.func(file_id=8, tool_call_id="call-attachments")

    assert result.ok is True
    assert result.data["attachmentStatus"] == "AVAILABLE"
    assert result.data["attachmentCount"] == 1
    assert result.data["attachments"] == [{"id": 51, "name": "活动方案.pdf", "type": "application/pdf", "size": 2048}]
    assert "url" not in str(result.data)


def test_list_party_file_categories_uses_list_response_contract(monkeypatch):
    emitted = []
    monkeypatch.setattr(query, "get_stream_writer", lambda: object())
    monkeypatch.setattr(query, "emit", lambda *args, **kwargs: emitted.append((args, kwargs)))
    monkeypatch.setattr(
        query,
        "java_get_list",
        lambda path: [{"id": 7, "name": "联调党务分类"}],
    )

    result = query.list_party_file_categories.func(tool_call_id="call-categories")

    assert result.ok is True
    assert result.data == [{"id": 7, "name": "联调党务分类"}]
    assert emitted[-1][1]["toolName"] == "list_party_file_categories"
