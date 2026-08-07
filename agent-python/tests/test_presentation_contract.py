import json

from src.tools.common.contracts import ToolError, ToolResponse, validate_tool_result, get_tool_contract
from src.tools.common.presentation import PresentationSpec, normalize_presentation, presentation_for_response


def test_legacy_card_is_adapted_without_dropping_legacy_fields():
    result = normalize_presentation(
        {"blockType": "card", "cardType": "approval_inbox", "view": "list"},
        data={"total": 23, "candidates": [{"taskId": "t-1"}], "excludedCount": 2},
    )

    assert result["cardType"] == "approval_inbox"
    assert result["resultKind"] == "record_list"
    assert result["primaryResult"] is True
    assert result["sourceResultId"].startswith("result:")
    assert result["observedScope"] == {
        "totalCount": 23,
        "excludedCount": 2,
        "returnedCount": 1,
    }
    assert result["displayPolicy"]["allowLoadMore"] is True


def test_explicit_contract_values_win_and_source_id_is_stable():
    presentation = {
        "resultKind": "ranked_list",
        "sourceResultId": "approval-query:run-1",
        "requestedScope": {"sortBy": "amount", "limit": 10},
        "summary": {"headline": "共 1 条可排序审批"},
        "actions": [{"id": "open", "label": "查看详情"}],
    }
    data = {"total": 23, "candidates": [{"taskId": "t-1", "amount": 180000}]}

    first = normalize_presentation(presentation, data=data)
    second = normalize_presentation(presentation, data=data)

    assert first == second
    assert first["resultKind"] == "ranked_list"
    assert first["sourceResultId"] == "approval-query:run-1"
    assert first["requestedScope"] == {"sortBy": "amount", "limit": 10}
    assert first["summary"]["headline"] == "共 1 条可排序审批"


def test_error_response_uses_error_result_kind():
    response = ToolResponse(
        ok=False,
        error=ToolError(code="FACADE_UNAVAILABLE", message="服务暂不可用"),
    )

    presentation_for_response(response)

    assert response.presentation["resultKind"] == "error"
    assert response.presentation["summary"] == {"headline": "服务暂不可用"}


def test_guarded_boundary_normalizes_tool_response_for_langchain():
    response = ToolResponse(
        ok=True,
        data={"total": 2, "items": [{"id": "a"}, {"id": "b"}]},
        presentation={"blockType": "card", "cardType": "todo"},
    )

    guarded = validate_tool_result(get_tool_contract("list_my_pending_approvals"), response)
    payload = json.loads(guarded.to_tool_content())

    assert payload["presentation"]["resultKind"] == "record_list"
    assert payload["presentation"]["observedScope"]["totalCount"] == 2


def test_party_file_approval_stays_a_control_flow_projection():
    response = ToolResponse(
        ok=True,
        data={"draftId": "draft-1", "approvalId": "approval-1"},
        presentation={"blockType": "card", "cardType": "party_file_approval"},
    )

    presentation_for_response(response)

    assert response.presentation == {
        "blockType": "card",
        "cardType": "party_file_approval",
    }


def test_presentation_spec_accepts_camel_case_transport_shape():
    spec = PresentationSpec.model_validate(
        {
            "resultKind": "analysis",
            "primaryResult": True,
            "sourceResultId": "analysis:1",
            "requestedScope": {},
            "observedScope": {"totalCount": 5},
            "summary": {"headline": "已完成分析"},
            "actions": [],
            "displayPolicy": {"defaultExpanded": False},
        }
    )

    assert spec.model_dump(by_alias=True)["sourceResultId"] == "analysis:1"
