from __future__ import annotations

import pickle
from types import SimpleNamespace

from langgraph.checkpoint.memory import InMemorySaver
import pytest

from src.domain.operation import OperationContext, bind_approval, patch_operation, transition_operation
from src.tools.common import tool_success
from src.tools.common.events import current_agent_context, set_event_context
from src.workflows.personal_schedule import graph as graph_module
from src.workflows.personal_schedule.contracts import PersonalScheduleWorkflowOutcome
from src.workflows.runtime import WorkflowRuntime
from src.workflows.runtime_context import get_workflow_runtime, reset_workflow_runtime, set_workflow_runtime
from src.tools.workflows.personal_schedule import run_personal_schedule_workflow


class _FakeOperationRuntime:
    """In-memory substitute for the required durable runtime boundary."""

    def __init__(self, *, action_id: str, payload: dict):
        context = current_agent_context()
        self.operation = OperationContext(
            operation_id="op-schedule-test",
            action_id=action_id,
            capability_id="schedule",
            tenant_id=str(context.get("tenantId") or "tenant-test"),
            user_id=str(context.get("userId") or "user-test"),
            thread_id=str(context.get("threadId") or "thread-test"),
            origin_run_id=str(context.get("originRunId") or context.get("runId") or "run-test"),
            current_run_id=str(context.get("runId") or "run-test"),
            message_id=str(context.get("messageId") or "message-test"),
            status="COLLECTING_INFO",
            payload=payload,
        )
        self.closed = False

    @property
    def operation_id(self):
        return self.operation.operation_id

    def transition(self, status, *, event_type=None, data=None):
        del event_type, data
        self.operation = transition_operation(self.operation, status, expected_version=self.operation.version)
        return self.operation

    def bind_approval(self, approval_id):
        self.operation = bind_approval(self.operation, str(approval_id), expected_version=self.operation.version)
        return self.operation

    def record_outcome(self, outcome):
        if str(outcome.get("status") or "") == "FAILED" and self.operation.status not in {"SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"}:
            self.transition("FAILED")
        self.operation = patch_operation(self.operation, expected_version=self.operation.version, result=dict(outcome))

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _required_operation_runtime(monkeypatch):
    class RuntimeFactory:
        @classmethod
        def start(cls, **kwargs):
            return _FakeOperationRuntime(
                action_id=str(kwargs["action_id"]),
                payload=dict(kwargs.get("payload") or {}),
            )

    monkeypatch.setattr(graph_module, "OperationRuntime", RuntimeFactory)


def test_workflow_normalizes_epoch_millis_from_java_source():
    assert graph_module._normalize_schedule_datetime(1786075200000) == "2026-08-07 12:00:00"
    assert graph_module._normalize_schedule_datetime("1786075200000") == "2026-08-07 12:00:00"


def test_schedule_macro_schema_is_structured():
    properties = run_personal_schedule_workflow.tool_call_schema.model_json_schema()["properties"]
    assert {"operation", "title", "start_time", "end_time", "source_schedule_id"} <= set(properties)


def test_schedule_workflow_rejects_update_without_target():
    result = graph_module.run_personal_schedule_workflow(operation="UPDATE")
    assert result.status == "NEEDS_INPUT"
    assert result.error_code == "SCHEDULE_TARGET_REQUIRED"


def test_schedule_workflow_runs_source_then_draft(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(graph_module, "get_stream_writer", lambda: None)
    monkeypatch.setattr(graph_module, "emit", lambda *args, **kwargs: None)

    def source(**kwargs):
        calls.append("source")
        return tool_success({"scheduleId": 17, "title": "旧日程"})

    def draft(**kwargs):
        calls.append("draft")
        return tool_success({
            "requires_confirmation": True,
            "draftId": "schedule-draft",
            "approvalId": "schedule-approval",
            "confirmation_token": "schedule-draft",
        })

    monkeypatch.setattr(graph_module, "get_personal_schedule", SimpleNamespace(func=source))
    monkeypatch.setattr(graph_module, "create_personal_schedule_draft", SimpleNamespace(func=draft))
    result = graph_module.run_personal_schedule_workflow(
        operation="UPDATE", source_schedule_id=17, title="新日程",
        start_time="2026-07-30 10:00:00", end_time="2026-07-30 11:00:00",
    )
    assert result.status == "DRAFT_READY"
    assert result.draft_id == "schedule-draft"
    assert calls == ["source", "draft"]


def test_schedule_update_keeps_java_source_fields_when_model_omits_them(monkeypatch):
    captured = {}
    monkeypatch.setattr(graph_module, "get_stream_writer", lambda: None)
    monkeypatch.setattr(graph_module, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(graph_module, "get_personal_schedule", SimpleNamespace(func=lambda **kwargs: tool_success({
        "sourceId": 17, "title": "旧日程", "startTime": "2026-08-03 12:00:00",
        "endTime": "2026-08-03 14:00:00", "location": "A101", "description": "原说明",
        "attendeeUserIds": [7, 8], "otherParticipants": "外部顾问",
    })))
    monkeypatch.setattr(graph_module, "create_personal_schedule_draft", SimpleNamespace(func=lambda **kwargs: captured.update(kwargs) or tool_success({
        "requires_confirmation": True, "draftId": "schedule-draft", "approvalId": "schedule-approval",
        "confirmation_token": "schedule-draft",
    })))

    result = graph_module.run_personal_schedule_workflow(
        operation="UPDATE", source_schedule_id=17,
        start_time="2026-08-03 14:00:00", end_time="2026-08-03 16:00:00",
    )

    assert result.status == "DRAFT_READY"
    assert captured["title"] == "旧日程"
    assert captured["location"] == "A101"
    assert captured["attendee_user_ids"] == [7, 8]


def test_schedule_workflow_binds_parent_context_inside_nested_graph(monkeypatch):
    set_event_context("run-parent", "thread-parent", tenant_id="tenant-7", user_id="42", message_id="message-parent")
    observed = {}

    def draft(**kwargs):
        observed.update(current_agent_context())
        return tool_success({
            "requires_confirmation": True,
            "draftId": "schedule-draft",
            "approvalId": "schedule-approval",
            "confirmation_token": "schedule-draft",
        })

    monkeypatch.setattr(graph_module, "get_stream_writer", lambda: None)
    monkeypatch.setattr(graph_module, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(graph_module, "create_personal_schedule_draft", SimpleNamespace(func=draft))

    result = graph_module.run_personal_schedule_workflow(
        operation="CREATE", title="评审", start_time="2026-08-03 15:00", end_time="2026-08-03 16:00",
    )

    assert result.status == "DRAFT_READY"
    assert {key: observed[key] for key in ("runId", "threadId", "tenantId", "userId", "messageId")} == {
        "runId": "run-parent", "threadId": "thread-parent", "tenantId": "tenant-7", "userId": "42", "messageId": "message-parent",
    }


def test_schedule_workflow_recovers_message_id_from_trusted_parent_state(monkeypatch):
    set_event_context("run-parent", "thread-parent", tenant_id="tenant-7", user_id="42", message_id="")
    observed = {}

    def draft(**kwargs):
        observed.update(current_agent_context())
        return tool_success({
            "requires_confirmation": True,
            "draftId": "schedule-draft",
            "approvalId": "schedule-approval",
            "confirmation_token": "schedule-draft",
        })

    monkeypatch.setattr(graph_module, "get_stream_writer", lambda: None)
    monkeypatch.setattr(graph_module, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(graph_module, "create_personal_schedule_draft", SimpleNamespace(func=draft))

    result = graph_module.run_personal_schedule_workflow(
        operation="CREATE", title="评审", start_time="2026-08-03 15:00", end_time="2026-08-03 16:00",
        parent_state={"current_user_message": {"trusted": True, "source": "current_human_message", "messageId": "message-from-state"}},
    )

    assert result.status == "DRAFT_READY"
    assert observed["messageId"] == "message-from-state"


def test_schedule_workflow_checkpoint_excludes_unpickleable_stream_writer(monkeypatch):
    emitted_writers: list[object] = []
    monkeypatch.setattr(
        graph_module,
        "emit",
        lambda writer, *args, **kwargs: emitted_writers.append(writer) or {},
    )

    def source(**kwargs):
        return tool_success({"scheduleId": 17, "title": "旧日程"})

    def draft(**kwargs):
        return tool_success({
            "requires_confirmation": True,
            "draftId": "schedule-draft",
            "approvalId": "schedule-approval",
            "confirmation_token": "schedule-draft",
        })

    monkeypatch.setattr(graph_module, "get_personal_schedule", SimpleNamespace(func=source))
    monkeypatch.setattr(graph_module, "create_personal_schedule_draft", SimpleNamespace(func=draft))

    def stream_writer(event: object) -> None:
        del event

    with pytest.raises((pickle.PicklingError, AttributeError, TypeError)):
        pickle.dumps(stream_writer)

    runtime_token = set_workflow_runtime(
        WorkflowRuntime("personal_schedule", writer=stream_writer, emit_fn=graph_module.emit)
    )
    try:
        graph = graph_module.build_personal_schedule_graph(checkpointer=InMemorySaver())
        result = graph.invoke(
            {
                "operation": "UPDATE",
                "source_schedule_id": 17,
                "title": "新日程",
                "start_time": "2026-07-30 10:00:00",
                "end_time": "2026-07-30 11:00:00",
            },
            {"configurable": {"thread_id": "schedule-checkpoint-test"}},
        )
    finally:
        reset_workflow_runtime(runtime_token)

    assert result["outcome"]["status"] == "DRAFT_READY"
    assert "workflow_runtime" not in result
    assert get_workflow_runtime() is None
    assert emitted_writers and all(writer is stream_writer for writer in emitted_writers)


def test_schedule_macro_passes_fields(monkeypatch):
    captured = {}

    def fake(**kwargs):
        captured.update(kwargs)
        return PersonalScheduleWorkflowOutcome(status="NEEDS_INPUT", message="缺字段")

    monkeypatch.setattr("src.tools.workflows.personal_schedule._run_workflow", fake)
    response = run_personal_schedule_workflow.func(
        operation="CREATE", title="周会", start_time="10:00", end_time="11:00",
        attendee_user_ids=[7], tool_call_id="schedule-call", state={"messages": []},
    )
    assert response.ok is True
    assert captured["operation"] == "CREATE"
    assert captured["attendee_user_ids"] == [7]


def test_current_user_message_id_is_used_when_run_metadata_omits_it():
    from langchain_core.messages import HumanMessage

    from src.orchestration.policies import CurrentUserMessageMiddleware
    from src.tools.common.events import current_agent_context, set_event_context

    set_event_context("run-message-context", "thread-message-context", message_id="")
    update = CurrentUserMessageMiddleware(trusted_source=True)._update(
        {"messages": [HumanMessage(content="创建日程", id="human-message-1")]}
    )

    assert update["current_user_message"]["messageId"] == "human-message-1"
    assert current_agent_context()["messageId"] == "human-message-1"


def test_trusted_checkpoint_message_id_is_restored_on_model_reentry():
    """A tool->model re-entry must retain the approval binding message id."""
    from src.orchestration.policies import CurrentUserMessageMiddleware
    from src.tools.common.events import current_agent_context, set_event_context

    set_event_context("run-reentry", "thread-reentry", message_id="")
    update = CurrentUserMessageMiddleware(trusted_source=True)._update(
        {
            "current_user_message": {
                "source": "current_human_message",
                "messageId": "original-turn-message",
                "text": "预约会议室",
                "trusted": True,
            },
            "messages": [],
        }
    )

    assert update is None
    assert current_agent_context()["messageId"] == "original-turn-message"


def test_hitl_resume_preserves_approval_bound_message_id():
    from langchain_core.messages import HumanMessage

    from src.orchestration.policies import CurrentUserMessageMiddleware
    from src.tools.common.events import current_agent_context, set_event_context

    set_event_context(
        "resume-run",
        "thread-resume",
        message_id="approval-message",
        origin_run_id="origin-run",
        resume_run_id="resume-run",
    )
    update = CurrentUserMessageMiddleware(trusted_source=True)._update(
        {
            "current_user_message": {
                "source": "current_human_message",
                "messageId": "original-human-message",
                "trusted": True,
            },
            "messages": [HumanMessage(content="创建日程", id="original-human-message")],
        }
    )

    assert update is None
    assert current_agent_context()["messageId"] == "approval-message"
