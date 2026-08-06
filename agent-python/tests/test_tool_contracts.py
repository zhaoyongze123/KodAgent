import json
from uuid import uuid4

import pytest
from langchain.tools import tool
from langgraph.errors import GraphBubbleUp, GraphInterrupt

from src.tools.common.contracts import ToolResponse, apply_tool_contracts
from src.tools.common.executor import invoke_tool
from src.tools.common.events import build_event, report_progress


def test_tool_response_serializes_to_canonical_json():
    response = ToolResponse(ok=True, data={"message": "ok"})

    content = response.to_tool_content()

    assert json.loads(content) == {"ok": True, "data": {"message": "ok"}}


def test_tool_response_keeps_ui_presentation_contract():
    response = ToolResponse(
        ok=True,
        data={"events": []},
        presentation={"blockType": "card", "cardType": "calendar"},
    )

    assert json.loads(response.to_tool_content())["presentation"] == {
        "blockType": "card",
        "cardType": "calendar",
    }


def test_contract_guard_returns_json_to_langchain_boundary():
    @tool
    def report_progress(stage: str, message: str) -> ToolResponse:
        """Test progress tool."""
        return ToolResponse(ok=True, data={"stage": stage, "message": message})

    apply_tool_contracts([report_progress])

    result = report_progress.invoke({"stage": "plan", "message": "开始处理"})

    assert isinstance(result, str)
    assert json.loads(result) == {
        "ok": True,
        "data": {"stage": "plan", "message": "开始处理"},
    }


def test_workflow_executor_uses_the_same_contract_boundary():
    @tool
    def report_progress(stage: str, message: str) -> ToolResponse:
        """Test workflow invocation."""
        return ToolResponse(ok=True, data={"stage": stage, "message": message})

    result = invoke_tool(report_progress, {"stage": "plan", "message": "工作流调用"})

    assert json.loads(result)["data"]["message"] == "工作流调用"


def test_workflow_executor_supplies_full_tool_call_for_injected_id(monkeypatch):
    """Deterministic graph calls must preserve LangChain's injected arguments."""
    monkeypatch.setattr(
        "src.tools.common.events.publish_narration",
        lambda *args, **kwargs: {
            "entryId": "call-injected",
            "data": {"stage": "plan"},
        },
    )
    monkeypatch.setattr("src.tools.common.events.sync_runtime_event_context", lambda: None)
    monkeypatch.setattr("src.tools.common.events.get_stream_writer", lambda: None)
    original_func = report_progress.func
    try:
        result = invoke_tool(
            report_progress,
            {
                "stage": "plan",
                "message": "工作流调用",
                "tool_call_id": f"call-{uuid4().hex}",
            },
        )
        assert json.loads(result)["data"]["recorded"] is True
    finally:
        # apply_tool_contracts wraps the shared Tool in place; keep this test
        # isolated from tests that call the Tool directly afterwards.
        report_progress.func = original_func


@pytest.mark.parametrize("control_flow_error", [GraphBubbleUp("bubble"), GraphInterrupt([])])
def test_contract_guard_re_raises_graph_control_flow(control_flow_error):
    @tool
    def report_progress(stage: str, message: str) -> ToolResponse:
        """Test control-flow propagation."""
        raise control_flow_error

    apply_tool_contracts([report_progress])

    with pytest.raises(type(control_flow_error)) as raised:
        report_progress.func(stage="plan", message="等待审批")

    assert raised.value is control_flow_error


def test_contract_guard_converts_ordinary_exception_to_tool_error():
    @tool
    def report_progress(stage: str, message: str) -> ToolResponse:
        """Test ordinary exception conversion."""
        raise ValueError("ordinary failure")

    apply_tool_contracts([report_progress])
    result = json.loads(report_progress.func(stage="plan", message="失败"))

    assert result["ok"] is False
    assert result["error"]["code"] == "TOOL_EXECUTION_FAILED"


def test_report_progress_hides_injected_tool_call_id_from_model_schema():
    assert set(report_progress.tool_call_schema.model_json_schema()["properties"]) == {
        "stage",
        "message",
    }


def test_event_keeps_tool_call_id_in_envelope():
    event = build_event("progress", {"toolCallId": "call-123"}, "正在处理")

    assert event["toolCallId"] == "call-123"
    assert "toolCallId" not in event["data"]
