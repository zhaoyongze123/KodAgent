import pytest

from src.orchestration.graph import build_checkpointer
from src.orchestration.tool_registry import business_tools, main_tools
from src.subagents.registry import build_subagents
from src.tools.common.contracts import get_tool_contract
import src.oa_agent as oa_agent_module


def test_parent_tool_registry_exposes_only_parent_boundary_tools():
    names = {tool.name for tool in main_tools()}

    assert "report_progress" in names
    assert "route_conversation" in names
    assert "confirm_meeting_booking" in names
    assert "confirm_approval_batch_action" in names
    assert "execute_approval_batch_action" not in names
    assert "run_approval_query_plan" in names
    assert "get_party_file_attachments" in names
    assert "search_party_files" not in names


def test_business_registry_contains_domain_contracts_and_four_subagents():
    names = {tool.name for tool in business_tools()}

    assert {"list_my_pending_approvals", "get_my_calendar", "search_party_files"} <= names
    assert "find_nearest_party_file_by_publish_time" not in names
    assert "confirm_approval_batch_action" in names
    assert "execute_approval_batch_action" not in names
    # Bare BPM mutation helpers may exist for legacy/internal callers, but
    # must never become model-visible Agent tools. Approval writes enter only
    # through preview + official HITL confirmation.
    assert {"approve_approval_task", "reject_approval_task", "submit_approval_request"}.isdisjoint(names)
    assert {item["name"] for item in build_subagents("2026-07-29 12:00:00")} == {
        "approvals_agent",
        "meeting_rooms_agent",
        "schedules_agent",
        "party_files_agent",
    }


def test_subagent_capability_boundaries_keep_party_receipts_and_approval_writes_safe():
    subagents = {item["name"]: item for item in build_subagents("2026-07-29 12:00:00")}
    approval_tools = {tool.name for tool in subagents["approvals_agent"]["tools"]}
    party_tools = {tool.name for tool in subagents["party_files_agent"]["tools"]}

    assert {"preview_approval_batch_action", "preview_approval_task_action"} <= approval_tools
    assert "find_nearest_party_file_by_publish_time" not in party_tools
    assert {"approve_approval_task", "reject_approval_task", "submit_approval_request", "confirm_approval_batch_action", "confirm_approval_task_action"}.isdisjoint(approval_tools)
    # Request submission stays unavailable to models until Java exposes a
    # durable approval-request draft plus the same ApprovalCard/HITL binding
    # used by meeting, schedule and task actions.
    # The main graph alone owns the official confirmation tools so the child
    # cannot invoke a raw BPM write from a natural-language response.
    assert {"confirm_approval_batch_action", "confirm_approval_task_action"} <= {
        tool.name for tool in main_tools()
    }

    assert {"get_party_file_detail", "get_party_file_attachment", "get_party_file_attachments"} <= party_tools
    assert {"get_manage_party_file", "create_party_file_draft", "update_party_file_draft", "delete_party_file_draft", "confirm_create_party_file", "confirm_update_party_file", "confirm_delete_party_file"}.isdisjoint(party_tools)
    assert {"create_party_file_draft", "update_party_file_draft", "delete_party_file_draft", "confirm_create_party_file", "confirm_update_party_file", "confirm_delete_party_file"} <= {tool.name for tool in main_tools()}
    for tool_name in ("get_party_file_detail", "get_party_file_attachment", "get_party_file_attachments"):
        contract = get_tool_contract(tool_name)
        assert contract.read_only is False
        assert contract.side_effect is True
        assert contract.approval_required is False
        assert contract.permission == "party-file:read"


def test_workflow_rollout_keeps_react_domain_fallbacks(monkeypatch):
    """Enabling deterministic paths must not remove uncovered domain agents."""
    monkeypatch.setenv("OA_AGENT_MEETING_WORKFLOW_V2", "true")
    monkeypatch.setenv("OA_AGENT_SCHEDULE_WORKFLOW_V2", "true")

    names = {item["name"] for item in build_subagents("2026-07-29 12:00:00")}
    assert names == {
        "approvals_agent",
        "meeting_rooms_agent",
        "schedules_agent",
        "party_files_agent",
    }

    parent_tools = {tool.name for tool in main_tools()}
    assert {"route_conversation", "run_meeting_booking_workflow", "run_personal_schedule_workflow"} <= parent_tools


def test_build_agent_keeps_meeting_react_child_when_workflow_is_enabled(monkeypatch):
    monkeypatch.setenv("OA_AGENT_MEETING_WORKFLOW_V2", "true")
    captured = {}

    monkeypatch.setattr(oa_agent_module, "ChatOpenAI", lambda **_: object())
    monkeypatch.setattr(oa_agent_module, "apply_tool_contracts", lambda tools: tools)
    monkeypatch.setattr(
        oa_agent_module,
        "create_deep_agent",
        lambda **kwargs: captured.update(kwargs) or object(),
    )

    oa_agent_module.build_agent(use_checkpointer=False)

    assert "run_meeting_booking_workflow" in {tool.name for tool in captured["tools"]}
    assert "meeting_rooms_agent" in {item["name"] for item in captured["subagents"]}


def test_graph_checkpointer_keeps_backend_selection_out_of_entrypoint(monkeypatch):
    monkeypatch.setenv("OA_AGENT_CHECKPOINTER", "memory")

    assert build_checkpointer().__class__.__name__ == "InMemorySaver"


def test_graph_checkpointer_requires_explicit_backend(monkeypatch):
    monkeypatch.delenv("OA_AGENT_CHECKPOINTER", raising=False)

    with pytest.raises(RuntimeError, match="OA_AGENT_CHECKPOINTER"):
        build_checkpointer()
