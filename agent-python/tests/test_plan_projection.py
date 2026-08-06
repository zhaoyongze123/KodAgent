import json
from types import SimpleNamespace

from langchain_core.messages import HumanMessage, ToolMessage

from src.orchestration.plan_projection import PlanToolProjectionMiddleware


def _request(messages, tools, tool_call=None):
    base = SimpleNamespace(state={"messages": messages}, tools=tools, tool_call=tool_call)
    return SimpleNamespace(
        **vars(base),
        override=lambda **kwargs: SimpleNamespace(**{**vars(base), **kwargs}),
    )


def test_projection_keeps_only_compiled_executor():
    route = {"ok": True, "data": {"planStatus": "RESOLVED", "executionTool": "execute_party_file_metadata_plan"}}
    messages = [ToolMessage(content=json.dumps(route), name="route_conversation", tool_call_id="r1")]
    keep = SimpleNamespace(name="execute_party_file_metadata_plan")
    hidden = SimpleNamespace(name="search_party_knowledge")
    request = _request(messages, [keep, hidden])

    projected = PlanToolProjectionMiddleware._override(request)

    assert [item.name for item in projected.tools] == ["execute_party_file_metadata_plan"]


def test_projection_blocks_task_when_registered_domain_has_no_action_id():
    """A provider retry may drop ACTION_SELECTION; the invariant still holds."""
    route = {
        "ok": True,
        "data": {
            "capabilityId": "approval_read",
            "planStatus": "CLARIFY",
            "routeDecision": {"capabilityId": "approval_read", "strategy": "clarify"},
        },
    }
    messages = [ToolMessage(content=json.dumps(route), name="route_conversation", tool_call_id="r1")]
    projected = PlanToolProjectionMiddleware._override(_request(messages, [
        SimpleNamespace(name="task"),
        SimpleNamespace(name="route_conversation"),
        SimpleNamespace(name="report_progress"),
        SimpleNamespace(name="run_approval_query_plan"),
    ]))

    assert set(item.name for item in projected.tools) == {
        "report_progress", "route_conversation"
    }


def test_projection_keeps_only_resolved_workflow_macro_tool():
    route = {"ok": True, "data": {"planStatus": "RESOLVED", "executionTool": "run_meeting_booking_workflow"}}
    messages = [ToolMessage(content=json.dumps(route), name="route_conversation", tool_call_id="r1")]
    workflow = SimpleNamespace(name="run_meeting_booking_workflow")
    unrelated = SimpleNamespace(name="update_meeting_booking_request")
    delegate = SimpleNamespace(name="task")

    projected = PlanToolProjectionMiddleware._override(_request(messages, [workflow, unrelated, delegate]))

    assert [item.name for item in projected.tools] == ["run_meeting_booking_workflow"]


def test_projection_keeps_only_party_file_create_draft_after_route_recovery():
    route = {
        "ok": True,
        "data": {
            "capabilityId": "party_file",
            "execution_class": "workflow",
            "planStatus": "RESOLVED",
            "executionTool": "create_party_file_draft",
        },
    }
    messages = [ToolMessage(content=json.dumps(route), name="route_conversation", tool_call_id="r1")]
    projected = PlanToolProjectionMiddleware._override(_request(messages, [
        SimpleNamespace(name="create_party_file_draft"),
        SimpleNamespace(name="party_files_agent"),
        SimpleNamespace(name="task"),
    ]))

    assert [item.name for item in projected.tools] == ["create_party_file_draft"]


def test_projection_keeps_delegation_for_fallback_plan():
    route = {"ok": True, "data": {"planStatus": "FALLBACK", "capability_id": "meeting"}}
    messages = [ToolMessage(content=json.dumps(route), name="route_conversation", tool_call_id="r1")]
    task = SimpleNamespace(name="task")
    unrelated = SimpleNamespace(name="run_meeting_booking_workflow")

    projected = PlanToolProjectionMiddleware._override(_request(messages, [task, unrelated]))

    assert [item.name for item in projected.tools] == ["task"]


def test_projection_keeps_domain_fallback_for_incomplete_approval_process_plan():
    route = {
        "ok": True,
        "data": {
            "capabilityId": "approval_process",
            "strategy": "delegate",
            "clarification": {"status": "CLARIFY"},
        },
    }
    messages = [ToolMessage(content=json.dumps(route), name="route_conversation", tool_call_id="r1")]
    projected = PlanToolProjectionMiddleware._override(_request(messages, [
        SimpleNamespace(name="task"),
        SimpleNamespace(name="run_approval_query_plan"),
    ]))

    assert [item.name for item in projected.tools] == ["task"]


def test_projection_does_not_delegate_failed_pending_query_to_application_scope():
    """A failed structured inbox plan must surface clarification, not switch scope."""
    route = {
        "ok": True,
        "data": {
            "capabilityId": "approval_read",
            "actionId": "approval.read.pending",
            "execution_class": "metadata_query",
            "planStatus": "UNSUPPORTED",
            "clarification": {
                "status": "UNSUPPORTED",
                "issues": ["不支持的审批排序字段：unknown"],
            },
        },
    }
    messages = [ToolMessage(content=json.dumps(route), name="route_conversation", tool_call_id="r1")]
    projected = PlanToolProjectionMiddleware._override(_request(messages, [
        SimpleNamespace(name="task"),
        SimpleNamespace(name="list_my_approval_applications"),
        SimpleNamespace(name="run_approval_query_plan"),
        SimpleNamespace(name="report_progress"),
    ]))

    assert {item.name for item in projected.tools} == {"report_progress"}


def test_projection_blocks_delegation_for_party_file_workflow_clarification():
    """Incomplete party-file writes must clarify instead of delegating to a read-only child."""
    route = {
        "ok": True,
        "data": {
            "capabilityId": "party_file",
            "execution_class": "workflow",
            "planStatus": "CLARIFY",
            "clarification": {"status": "CLARIFY"},
        },
    }
    messages = [ToolMessage(content=json.dumps(route), name="route_conversation", tool_call_id="r1")]
    projected = PlanToolProjectionMiddleware._override(_request(messages, [
        SimpleNamespace(name="task"),
        SimpleNamespace(name="report_progress"),
        SimpleNamespace(name="party_files_agent"),
    ]))

    assert [item.name for item in projected.tools] == ["report_progress"]


def test_projection_hides_tools_after_plan_result_for_synthesis():
    route = {"ok": True, "data": {"planStatus": "RESOLVED", "executionTool": "execute_party_file_metadata_plan"}}
    messages = [
        ToolMessage(content=json.dumps(route), name="route_conversation", tool_call_id="r1"),
        ToolMessage(content='{"ok":true}', name="execute_party_file_metadata_plan", tool_call_id="p1"),
    ]
    request = _request(messages, [SimpleNamespace(name="execute_party_file_metadata_plan")])

    projected = PlanToolProjectionMiddleware._override(request)

    assert projected.tools == []


def test_projection_never_reexposes_confirmation_tool_for_pending_schedule():
    route = {"ok": True, "data": {"planStatus": "RESOLVED", "executionTool": "run_personal_schedule_workflow"}}
    messages = [
        ToolMessage(content=json.dumps(route), name="route_conversation", tool_call_id="r1"),
        ToolMessage(content='{"ok":true,"data":{"requires_confirmation":true}}', name="run_personal_schedule_workflow", tool_call_id="p1"),
    ]
    confirm = SimpleNamespace(name="confirm_personal_schedule")
    projected = PlanToolProjectionMiddleware._override(_request(messages, [confirm]))

    assert projected.tools == []


def test_projection_injects_canonical_plan_into_empty_executor_call():
    canonical = {
        "entity": "party_file",
        "operation": "metadata_query",
        "filters": [],
        "rank": {"field": "publishTime", "mode": "nearest", "target": "2026-07-10"},
        "limit": 1,
        "projection": ["id", "title", "publishTime"],
        "execution_order": ["filter", "rank", "limit", "project"],
    }
    route = {
        "ok": True,
        "data": {
            "planStatus": "RESOLVED",
            "executionTool": "execute_party_file_metadata_plan",
            "executionPlan": canonical,
        },
    }
    messages = [ToolMessage(content=json.dumps(route), name="route_conversation", tool_call_id="r1")]
    request = _request(
        messages,
        [],
        {"name": "execute_party_file_metadata_plan", "args": {}, "id": "p1", "type": "tool_call"},
    )

    injected = PlanToolProjectionMiddleware._inject_compiled_plan(request)

    assert injected.tool_call["args"] == {"plan": canonical}


def test_projection_preserves_workflow_business_arguments_and_binds_operation():
    route = {
        "ok": True,
        "data": {
            "planStatus": "RESOLVED",
            "executionTool": "run_meeting_booking_workflow",
            "executionPlan": {"workflowType": "meeting_booking", "operation": "BOOK"},
        },
    }
    messages = [ToolMessage(content=json.dumps(route), name="route_conversation", tool_call_id="r1")]
    call = {
        "name": "run_meeting_booking_workflow",
        "args": {"subject": "预算评审", "start_time": "2026-08-01 10:00:00"},
        "id": "w1",
        "type": "tool_call",
    }

    injected = PlanToolProjectionMiddleware._inject_compiled_plan(_request(messages, [], call))

    assert injected.tool_call["args"] == {**call["args"], "operation": "BOOK"}


def test_projection_fills_missing_route_message_from_current_user_turn():
    request = _request(
        [HumanMessage(content="查发布时间最接近 2026 年 7 月 10 日的党务文件")],
        [],
        {"name": "route_conversation", "args": {}, "id": "r1", "type": "tool_call"},
    )

    injected = PlanToolProjectionMiddleware._inject_compiled_plan(request)

    assert injected.tool_call["args"] == {"message": "查发布时间最接近 2026 年 7 月 10 日的党务文件"}
