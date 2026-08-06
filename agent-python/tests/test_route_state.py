import json

from langchain_core.messages import HumanMessage, ToolMessage

from src.orchestration.route_state import (
    current_turn_messages,
    is_terminal_structured_failure,
    route_requires_action_selection,
    route_result,
)


def _route(data: dict) -> ToolMessage:
    return ToolMessage(
        name="route_conversation",
        tool_call_id="route-1",
        content=json.dumps({"ok": True, "data": data}, ensure_ascii=False),
    )


def test_route_result_uses_latest_route_in_current_turn_and_unwraps_data():
    messages = [
        HumanMessage("旧请求"),
        _route({"planStatus": "RESOLVED", "executionTool": "old_tool"}),
        HumanMessage("新请求"),
        _route({"planStatus": "RESOLVED", "executionTool": "new_tool"}),
    ]
    assert route_result(current_turn_messages(messages))["executionTool"] == "new_tool"


def test_route_state_requires_action_selection_without_reopening_tools():
    route = {"planStatus": "CLARIFY", "capabilityId": "meeting", "routePhase": "ACTION_SELECTION"}
    assert route_requires_action_selection(route)
    assert not is_terminal_structured_failure(route)


def test_route_state_treats_registered_structured_failure_as_terminal():
    route = {
        "planStatus": "UNSUPPORTED",
        "capabilityId": "party_file",
        "executionClass": "workflow",
        "actionId": "party_file.publish",
    }
    assert is_terminal_structured_failure(route)
