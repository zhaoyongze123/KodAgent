from src.orchestration.phase_prompt import MAIN_AGENT_PLANNING_PROMPT
from types import SimpleNamespace
from src.orchestration.plan_projection import PlanToolProjectionMiddleware


def test_party_file_write_prompt_selects_operation_specific_main_tools():
    assert "CREATE 只能调用 create_party_file_draft" in MAIN_AGENT_PLANNING_PROMPT
    assert "UPDATE 只能调用 update_party_file_draft" in MAIN_AGENT_PLANNING_PROMPT
    assert "DELETE 只能调用 delete_party_file_draft" in MAIN_AGENT_PLANNING_PROMPT


def test_party_file_create_projection_injects_only_compiled_operation():
    route = {"planStatus": "RESOLVED", "executionTool": "create_party_file_draft", "executionPlan": {"operation": "CREATE", "version": "1"}}
    request = SimpleNamespace(
        tool_call={"name": "create_party_file_draft", "args": {"operation": "DELETE", "title": "通知"}},
        state={"messages": [{"type": "human", "content": "发布通知"}, {"type": "tool", "name": "route_conversation", "content": {"data": route}}]},
        override=lambda **kwargs: kwargs,
    )
    assert PlanToolProjectionMiddleware._inject_compiled_plan(request)["tool_call"]["args"]["operation"] == "CREATE"
