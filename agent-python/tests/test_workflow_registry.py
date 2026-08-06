from __future__ import annotations

from src.tools.common.events import set_event_context
from src.workflows.contracts import ConfirmationPolicy, WorkflowContract
from src.workflows.registry import WorkflowRegistry, confirmation_route, workflow_registry
from src.workflows.runtime import WorkflowRuntime


def test_meeting_workflow_is_registered_with_boundary_contract():
    contract = workflow_registry.require("meeting_booking")

    assert contract.tool_name == "run_meeting_booking_workflow"
    assert contract.confirmation_policy.required is True
    assert contract.confirmation_policy.tool_name == "confirm_meeting_booking"
    assert contract.feature_flag == "OA_AGENT_MEETING_WORKFLOW_V2"
    assert "subject" in (contract.metadata()["inputSchema"]["properties"])
    assert "status" in (contract.metadata()["outcomeSchema"]["properties"])
    assert confirmation_route("meeting_booking") == {
        "workflowType": "meeting_booking",
        "toolName": "confirm_meeting_booking",
        "cardType": "meeting_booking",
        "version": "1",
    }


def test_personal_schedule_workflow_is_registered_and_opt_in(monkeypatch):
    contract = workflow_registry.require("personal_schedule")
    assert contract.tool_name == "run_personal_schedule_workflow"
    assert contract.confirmation_policy.tool_name == "confirm_personal_schedule"
    assert not contract.is_enabled({})
    assert contract.is_enabled({"OA_AGENT_SCHEDULE_WORKFLOW_V2": "true"})


def test_registry_rejects_duplicates_and_resolves_feature_flags():
    contract = WorkflowContract(
        workflow_type="demo",
        tool_name="run_demo",
        input_schema=None,
        outcome_schema=None,
        confirmation_policy=ConfirmationPolicy(),
        feature_flag="TEST_WORKFLOW_ENABLED",
    )
    registry = WorkflowRegistry([contract])

    assert registry.enabled("demo", environ={"TEST_WORKFLOW_ENABLED": "true"})
    assert not registry.enabled("demo", environ={"TEST_WORKFLOW_ENABLED": "off"})
    try:
        registry.register(contract)
    except ValueError as exc:
        assert "工作流已注册" in str(exc)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("duplicate workflow registration should fail")


def test_workflow_runtime_emits_standard_lifecycle_contracts(monkeypatch):
    set_event_context("run-workflow-runtime", "thread-workflow-runtime", message_id="message-runtime")
    events = []

    def capture(writer, event_type, text, **data):
        events.append({"type": event_type, "text": text, "data": data})
        return events[-1]

    runtime = WorkflowRuntime("meeting_booking", writer=lambda value: None, emit_fn=capture)
    runtime.started()
    runtime.node_started("prepare_request")
    runtime.node_completed("prepare_request")
    runtime.blocked("create_draft")
    runtime.failed("预约失败", node="create_draft", errorCode="JAVA_UNAVAILABLE")
    runtime.completed()

    assert [item["type"] for item in events] == [
        "workflow.started",
        "workflow.node.started",
        "workflow.node.completed",
        "workflow.blocked",
        "workflow.failed",
        "workflow.completed",
    ]
    assert all(item["data"]["workflowType"] == "meeting_booking" for item in events)
    assert events[1]["data"]["workflowNode"] == "prepare_request"
    assert events[3]["data"]["workflowStatus"] == "blocked"
    assert events[4]["data"]["errorCode"] == "JAVA_UNAVAILABLE"
    assert all(len(item["data"]["eventId"]) <= 128 for item in events)


def test_workflow_runtime_run_emits_completion_and_rethrows_failure():
    events = []

    def capture(writer, event_type, text, **data):
        events.append(event_type)
        return {"type": event_type}

    runtime = WorkflowRuntime("demo", emit_fn=capture)
    assert runtime.run(lambda: 42) == 42
    assert events == ["workflow.started", "workflow.completed"]

    events.clear()
    try:
        runtime.run(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    except RuntimeError as exc:
        assert str(exc) == "boom"
    else:  # pragma: no cover - assertion branch
        raise AssertionError("workflow runtime should rethrow runner failure")
    assert events == ["workflow.started", "workflow.failed"]
