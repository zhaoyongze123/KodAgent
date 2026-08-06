from src.domain.entities import PartyFile, PartyFileAttachment
from src.integration.oa_client import JavaFacadeClient
from src.tools.common.contracts import apply_tool_contracts
from src.tools.common.http_client import JavaFacadeHttpError
from src.orchestration.capabilities import resolve_action
from src.orchestration.planning.common import copy_registered_fields
from src.orchestration.tool_registry import business_tools, main_tools
from src.tools.common.contracts import TOOL_CONTRACTS


def test_every_model_visible_tool_has_a_contract_and_unique_name():
    for tools in (business_tools(), main_tools()):
        names = [str(tool.name) for tool in tools]
        assert len(names) == len(set(names))
        assert set(names) <= set(TOOL_CONTRACTS)


def test_copy_registered_fields_uses_action_catalog_field_specs():
    action = resolve_action("approval_read", "approval.read.pending")
    assert action is not None
    copied = copy_registered_fields(
        {"filters": [{"field": "amount"}], "sort": {"field": "createdTime"}, "untrusted": "drop"}, action
    )
    assert copied == {"filters": [{"field": "amount"}], "sort": {"field": "createdTime"}}


def test_operation_without_action_id_cannot_select_an_executor():
    assert resolve_action("meeting", None, "CREATE") is None


def test_domain_read_models_keep_human_fields_and_unknown_oa_metadata():
    file = PartyFile.model_validate(
        {
            "id": 7,
            "title": "通知",
            "categoryId": 2,
            "categoryName": "制度文件",
            "attachments": [{"id": 9, "fileName": "正文.docx", "downloadUrl": "/download/9"}],
            "newOaField": "forward-compatible",
        }
    )
    assert file.category_name == "制度文件"
    assert isinstance(file.attachments[0], PartyFileAttachment)
    assert file.attachments[0].file_name == "正文.docx"
    assert file.model_extra["newOaField"] == "forward-compatible"


def test_java_facade_client_keeps_identity_explicit(monkeypatch):
    calls = []

    def fake_post(path, payload, *, identity=None):
        calls.append((path, payload, identity))
        return {"ok": True}

    monkeypatch.setattr("src.integration.oa_client.java_post", fake_post)
    client = JavaFacadeClient(identity=("user-1", "tenant-1"))
    assert client.post("/agent/test", {"value": 1}) == {"ok": True}
    assert calls == [("/agent/test", {"value": 1}, ("user-1", "tenant-1"))]


def test_tool_boundary_preserves_http_authorization_classification():
    from langchain.tools import tool
    import json

    @tool("get_current_meeting_user")
    def fake_user() -> dict:
        """Test authorization failure mapping."""
        raise JavaFacadeHttpError(403, "/agent/tools/users/me")

    apply_tool_contracts([fake_user])
    result = json.loads(fake_user.func())
    assert result["error"]["code"] == "JAVA_FACADE_HTTP_403"
    assert result["error"]["kind"] == "authorization"
    assert result["error"]["details"] == {"statusCode": 403}
