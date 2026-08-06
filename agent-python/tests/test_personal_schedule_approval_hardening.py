from __future__ import annotations

from types import SimpleNamespace

from src.orchestration.routing.recovery_handlers.schedule import schedule_follow_up_plan
from src.tools.common import tool_failure
from src.workflows.personal_schedule import graph as graph_module


def _facts(candidates: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(facts={"schedule_query": {"editableCandidates": candidates}})


def test_schedule_follow_up_ignores_meetings_and_non_editable_records():
    result = schedule_follow_up_plan(
        "把刚才日程改到 16 点",
        _facts([
            {"sourceType": "MEETING_BOOKING", "sourceId": 38, "editable": True},
            {"sourceType": "PERSONAL_SCHEDULE", "sourceId": 17, "editable": False},
            {"sourceType": "PERSONAL_SCHEDULE", "sourceId": 18, "editable": True},
        ]),
    )

    assert result["status"] == "RESOLVED"
    assert result["source_schedule_id"] == 18


def test_schedule_follow_up_rejects_an_unlisted_explicit_id():
    result = schedule_follow_up_plan(
        "取消日程 999",
        _facts([{"sourceType": "PERSONAL_SCHEDULE", "sourceId": 17, "editable": True}]),
    )

    assert result["status"] == "CLARIFY"
    assert result["options"] == []


def test_personal_schedule_workflow_requires_source_for_update(monkeypatch):
    monkeypatch.setattr(graph_module, "OperationRuntime", SimpleNamespace(start=lambda **kwargs: None))

    result = graph_module.run_personal_schedule_workflow(
        operation="UPDATE",
        title="新标题",
        parent_state={"messages": []},
    )

    assert result.status == "NEEDS_INPUT"
    assert result.error_code == "SCHEDULE_TARGET_REQUIRED"


def test_personal_schedule_source_errors_remain_structured(monkeypatch):
    monkeypatch.setattr(graph_module, "OperationRuntime", SimpleNamespace(start=lambda **kwargs: None))
    monkeypatch.setattr(
        graph_module,
        "get_personal_schedule",
        SimpleNamespace(func=lambda **kwargs: tool_failure("SCHEDULE_NOT_FOUND", "日程不存在或无权访问")),
    )

    result = graph_module.run_personal_schedule_workflow(
        operation="CANCEL",
        source_schedule_id=17,
        parent_state={"messages": []},
    )

    assert result.status == "FAILED"
    assert result.error_code == "SCHEDULE_NOT_FOUND"
