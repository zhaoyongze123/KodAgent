from src.orchestration.compiler import compile_task_plan
from src.orchestration.compiler import infer_workflow_capability


def test_party_metadata_plan_compiles_to_one_executor():
    result = compile_task_plan(
        capability_id="party_file",
        execution_class="metadata_query",
        candidate_plan={
            "rank": {"field": "publishTime", "mode": "nearest", "target": "2026-07-10"},
            "limit": 1,
            "projection": ["id", "title", "publishTime"],
        },
    )

    assert result is not None
    assert result.status == "RESOLVED"
    assert result.execution_tool == "execute_party_file_metadata_plan"
    assert result.canonical["execution_order"] == ["filter", "rank", "limit", "project"]
    assert "search_party_knowledge" not in str(result.model_dump())


def test_party_metadata_plan_rejects_unknown_semantic_field():
    result = compile_task_plan(
        capability_id="party_file",
        execution_class="metadata_query",
        candidate_plan={
            "rank": {"field": "contentSimilarity", "mode": "desc"},
        },
    )

    assert result is not None
    assert result.status == "UNSUPPORTED"
    assert result.execution_tool is None


def test_party_file_write_plan_projects_only_operation_draft_tool():
    assert compile_task_plan(
        capability_id="party_file", execution_class="workflow",
        candidate_plan={"action_id": "party_file.create", "operation": "CREATE",
                        "title": "通知", "content": "正文", "category_name": "通知公告"},
    ).execution_tool == "create_party_file_draft"
    update = compile_task_plan(
        capability_id="party_file", execution_class="workflow",
        candidate_plan={"action_id": "party_file.update", "operation": "UPDATE",
                        "source_party_file_id": 42, "_authorized_source_fields": ["source_party_file_id"],
                        "title": "新通知"},
    )
    delete = compile_task_plan(
        capability_id="party_file", execution_class="workflow",
        candidate_plan={"action_id": "party_file.delete", "operation": "DELETE",
                        "source_party_file_id": 42, "_authorized_source_fields": ["source_party_file_id"]},
    )
    assert update.execution_tool == "update_party_file_draft"
    assert update.canonical["sourcePartyFileId"] == 42
    assert delete.execution_tool == "delete_party_file_draft"
    assert delete.canonical["sourcePartyFileId"] == 42
    assert compile_task_plan(
        capability_id="party_file", execution_class="workflow",
        candidate_plan={"action_id": "party_file.update", "operation": "UPDATE"},
    ).status == "CLARIFY"


def test_approval_query_uses_existing_canonical_plan():
    result = compile_task_plan(
        capability_id="approval_read",
        execution_class="metadata_query",
        query_intent={
            "action_id": "approval.read.pending",
            "entity": "pending_approval",
            "operation": "rank",
            "sort": [{"field": "amount", "direction": "DESC"}],
            "limit": 5,
        },
    )

    assert result is not None
    assert result.status == "RESOLVED"
    assert result.execution_tool == "run_approval_query_plan"


def test_enabled_meeting_workflow_compiles_to_registered_macro_tool(monkeypatch):
    monkeypatch.setenv("OA_AGENT_MEETING_WORKFLOW_V2", "true")

    result = compile_task_plan(
        capability_id="meeting",
        execution_class="workflow",
        candidate_plan={
            "action_id": "meeting.create", "operation": "BOOK",
            "subject": "验收会议", "start_time": "2026-08-06 10:00:00", "end_time": "2026-08-06 11:00:00",
        },
    )

    assert result is not None
    assert result.status == "RESOLVED"
    assert result.execution_tool == "run_meeting_booking_workflow"
    assert result.canonical == {
        "workflowType": "meeting_booking",
        "operation": "BOOK",
        "version": "1",
        "subject": "验收会议",
        "start_time": "2026-08-06 10:00:00",
        "end_time": "2026-08-06 11:00:00",
    }


def test_enabled_schedule_workflow_compiles_to_registered_macro_tool(monkeypatch):
    monkeypatch.setenv("OA_AGENT_SCHEDULE_WORKFLOW_V2", "true")

    result = compile_task_plan(
        capability_id="schedule",
        execution_class="workflow",
        candidate_plan={
            "action_id": "schedule.update", "operation": "UPDATE",
            "source_schedule_id": 17, "_authorized_source_fields": ["source_schedule_id"],
            "title": "更新日程",
        },
    )

    assert result is not None
    assert result.status == "RESOLVED"
    assert result.execution_tool == "run_personal_schedule_workflow"
    assert result.canonical["operation"] == "UPDATE"


def test_schedule_metadata_query_compiles_to_calendar_reader():
    result = compile_task_plan(
        capability_id="schedule",
        execution_class="metadata_query",
        candidate_plan={"action_id": "schedule.query", "operation": "QUERY", "date": "2026-08-07"},
    )
    assert result is not None
    assert result.status == "RESOLVED"
    assert result.execution_tool == "get_my_calendar"
    assert result.canonical["startTime"] == "2026-08-07 00:00:00"
    assert result.canonical["endTime"] == "2026-08-07 23:59:59"


def test_schedule_action_alias_compiles_to_registered_macro_tool(monkeypatch):
    monkeypatch.setenv("OA_AGENT_SCHEDULE_WORKFLOW_V2", "true")

    result = compile_task_plan(
        capability_id="schedule",
        execution_class="workflow",
        candidate_plan={
            "action_id": "schedule.create", "action": "create_schedule",
            "title": "日程", "start_time": "2026-08-07 09:00:00", "end_time": "2026-08-07 10:00:00",
        },
    )

    assert result is not None
    assert result.status == "RESOLVED"
    assert result.execution_tool == "run_personal_schedule_workflow"
    assert result.canonical["operation"] == "CREATE"


def test_schedule_type_alias_compiles_to_registered_macro_tool(monkeypatch):
    monkeypatch.setenv("OA_AGENT_SCHEDULE_WORKFLOW_V2", "true")

    result = compile_task_plan(
        capability_id="schedule",
        execution_class="workflow",
        candidate_plan={
            "action_id": "schedule.create", "type": "personal_schedule",
            "title": "日程", "start_time": "2026-08-07 09:00:00", "end_time": "2026-08-07 10:00:00",
        },
    )

    assert result is not None
    assert result.status == "RESOLVED"
    assert result.execution_tool == "run_personal_schedule_workflow"
    assert result.canonical["operation"] == "CREATE"


def test_typed_workflow_operation_can_recover_omitted_domain():
    assert infer_workflow_capability({"action": "create_personal_schedule"}) == "schedule"
    assert infer_workflow_capability({"action": "create_draft"}) == "schedule"
    assert infer_workflow_capability({"type": "personal_schedule"}) == "schedule"
    assert infer_workflow_capability({"action": "unknown"}) is None


def test_generic_create_does_not_default_to_meeting():
    assert infer_workflow_capability({"operation": "CREATE"}) is None


def test_explicit_party_file_entity_recovers_party_file_write_domain():
    assert infer_workflow_capability({"operation": "CREATE", "object_type": "party_file"}) == "party_file"


def test_meeting_update_and_cancel_compile_to_registered_macro_tool(monkeypatch):
    monkeypatch.setenv("OA_AGENT_MEETING_WORKFLOW_V2", "true")

    update = compile_task_plan(
        capability_id="meeting",
        execution_class="workflow",
        candidate_plan={
            "action_id": "meeting.update", "operation": "UPDATE",
            "source_booking_id": 40, "_authorized_source_fields": ["source_booking_id"],
            "start_time": "2026-08-06 14:00:00", "end_time": "2026-08-06 15:00:00",
        },
    )
    cancel = compile_task_plan(
        capability_id="meeting",
        execution_class="workflow",
        candidate_plan={
            "action_id": "meeting.cancel", "operation": "CANCEL",
            "source_booking_id": 40, "_authorized_source_fields": ["source_booking_id"],
        },
    )

    assert update is not None and update.status == "RESOLVED"
    assert update.execution_tool == "run_meeting_booking_workflow"
    assert update.canonical["operation"] == "UPDATE"
    assert cancel is not None and cancel.status == "RESOLVED"
    assert cancel.execution_tool == "run_meeting_booking_workflow"
    assert cancel.canonical["operation"] == "CANCEL"
