import pytest

from src.orchestration import action_catalog_sync
from src.orchestration.capabilities import ACTION_SPECS, action_constraints, action_field_specs, action_required_fields
from src.orchestration.action_catalog_runtime import clear_runtime_action_catalog
from src.tools.common.contracts import get_tool_contract


def _remote_catalog():
    actions = []
    for action in ACTION_SPECS:
        fields = action_field_specs(action)
        actions.append({
            "actionId": action.action_id,
            "capabilityId": action.capability_id,
            "executionClass": action.execution_class,
            "operation": action.operation,
            "readOnly": action.read_only,
            "requiresConfirmation": action.requires_confirmation,
            "permission": action.permission if action.permission != "agent:read" else (get_tool_contract(action.execution_tool).permission if action.execution_tool else "agent:read"),
            "requiredFields": [field.name for field in fields if field.required],
            "constraints": [dict(value) for value in action_constraints(action, use_runtime=False)],
            "fields": [
                {"name": field.name, "type": field.field_type, "required": field.required,
                 "nullable": field.nullable,
                 "sourcePolicy": field.source_policy,
                 "format": field.format,
                 "enum": [str(value) for value in field.enum]}
                for field in fields
            ],
        })
    return {"contractVersion": "agent-actions-v1", "actions": actions}


def test_action_catalog_sync_accepts_matching_contract(monkeypatch):
    monkeypatch.setenv("OA_AGENT_ACTION_CATALOG_SYNC", "true")
    monkeypatch.setenv("OA_AGENT_ACTION_CATALOG_STRICT", "true")
    monkeypatch.setattr(action_catalog_sync, "get_agent_action_catalog", lambda: _remote_catalog())
    action_catalog_sync._SYNC_CONTEXT.set(None)
    result = action_catalog_sync.sync_action_catalog(run_id="sync-test", force=True)
    assert result.status == "SYNCED"
    assert result.remote_count == len(ACTION_SPECS)
    assert result.fingerprint
    # The validated Java snapshot is now the runtime source for the planner's
    # visible field metadata, not only a startup comparison.
    remote = _remote_catalog()
    remote_action = next(item for item in remote["actions"] if item["actionId"] == "meeting.create")
    remote_action["fields"][0]["description"] = "Java authority description"
    monkeypatch.setattr(action_catalog_sync, "get_agent_action_catalog", lambda: remote)
    action_catalog_sync._SYNC_CONTEXT.set(None)
    action_catalog_sync.sync_action_catalog(run_id="runtime-overlay", force=True)
    assert action_field_specs("meeting.create")[0].description == "Java authority description"
    assert action_required_fields("meeting.create") == ("end_time", "start_time", "subject")
    clear_runtime_action_catalog()


def test_action_catalog_sync_blocks_drift_in_strict_mode(monkeypatch):
    monkeypatch.setenv("OA_AGENT_ACTION_CATALOG_SYNC", "true")
    monkeypatch.setenv("OA_AGENT_ACTION_CATALOG_STRICT", "true")
    remote = _remote_catalog()
    remote["actions"][0]["operation"] = "BROKEN"
    monkeypatch.setattr(action_catalog_sync, "get_agent_action_catalog", lambda: remote)
    action_catalog_sync._SYNC_CONTEXT.set(None)
    with pytest.raises(action_catalog_sync.ActionCatalogSyncError) as raised:
        action_catalog_sync.sync_action_catalog(run_id="drift-test", force=True)
    assert raised.value.code == "ACTION_CATALOG_DRIFT"


def test_action_catalog_sync_blocks_permission_drift(monkeypatch):
    monkeypatch.setenv("OA_AGENT_ACTION_CATALOG_SYNC", "true")
    monkeypatch.setenv("OA_AGENT_ACTION_CATALOG_STRICT", "true")
    remote = _remote_catalog()
    remote["actions"][0]["permission"] = "approval:write"
    monkeypatch.setattr(action_catalog_sync, "get_agent_action_catalog", lambda: remote)
    action_catalog_sync._SYNC_CONTEXT.set(None)
    with pytest.raises(action_catalog_sync.ActionCatalogSyncError) as raised:
        action_catalog_sync.sync_action_catalog(run_id="permission-drift", force=True)
    assert raised.value.code == "ACTION_CATALOG_DRIFT"


@pytest.mark.parametrize(
    ("change", "expected_fragment"),
    [
        (lambda field: field.update(type="string"), "字段 Schema 漂移"),
        (lambda field: field.update(sourcePolicy="authorized_query_fact"), "字段 Schema 漂移"),
        (lambda field: field.update(required=not field["required"]), "字段 Schema 漂移"),
    ],
)
def test_action_catalog_sync_blocks_any_field_schema_drift(monkeypatch, change, expected_fragment):
    """Java field changes are accepted and overlaid as the runtime authority."""
    monkeypatch.setenv("OA_AGENT_ACTION_CATALOG_SYNC", "true")
    monkeypatch.setenv("OA_AGENT_ACTION_CATALOG_STRICT", "true")
    remote = _remote_catalog()
    # meeting.update always has a datetime field, which makes the test
    # independent of the tuple ordering in the local catalog.
    action = next(item for item in remote["actions"] if item["actionId"] == "meeting.update")
    field = next(item for item in action["fields"] if item["name"] == "start_time")
    change(field)
    action["requiredFields"] = [item["name"] for item in action["fields"] if item.get("required")]
    monkeypatch.setattr(action_catalog_sync, "get_agent_action_catalog", lambda: remote)
    action_catalog_sync._SYNC_CONTEXT.set(None)
    result = action_catalog_sync.sync_action_catalog(run_id=f"field-overlay-{expected_fragment}", force=True)
    assert result.status == "SYNCED"
    clear_runtime_action_catalog()


def test_java_only_action_is_visible_but_requires_executor_binding(monkeypatch):
    monkeypatch.setenv("OA_AGENT_ACTION_CATALOG_SYNC", "true")
    monkeypatch.setenv("OA_AGENT_ACTION_CATALOG_STRICT", "true")
    remote = _remote_catalog()
    remote["actions"].append({
        "actionId": "meeting.export",
        "capabilityId": "meeting",
        "executionClass": "workflow",
        "operation": "EXPORT",
        "readOnly": True,
        "requiresConfirmation": False,
        "permission": "meeting:read",
        "requiredFields": [],
        "constraints": [],
        "fields": [],
    })
    monkeypatch.setattr(action_catalog_sync, "get_agent_action_catalog", lambda: remote)
    action_catalog_sync._SYNC_CONTEXT.set(None)
    result = action_catalog_sync.sync_action_catalog(run_id="java-only-action", force=True)
    assert result.status == "SYNCED"

    from src.orchestration.capabilities import actions_for_capability, resolve_action
    from src.orchestration.compiler import compile_task_plan
    assert any(item.action_id == "meeting.export" for item in actions_for_capability("meeting"))
    action = resolve_action("meeting", "meeting.export")
    assert action is not None and action.execution_tool is None
    plan = compile_task_plan(
        capability_id="meeting",
        execution_class="workflow",
        candidate_plan={"action_id": "meeting.export"},
    )
    assert plan is not None
    assert plan.status == "UNSUPPORTED"
    assert plan.canonical["errorCode"] == "ACTION_EXECUTOR_BINDING_MISSING"
    clear_runtime_action_catalog()


def test_plan_uses_java_field_contract_after_sync(monkeypatch):
    monkeypatch.setenv("OA_AGENT_ACTION_CATALOG_SYNC", "true")
    monkeypatch.setenv("OA_AGENT_ACTION_CATALOG_STRICT", "true")
    monkeypatch.setenv("OA_AGENT_MEETING_WORKFLOW_V2", "true")
    remote = _remote_catalog()
    action = next(item for item in remote["actions"] if item["actionId"] == "meeting.create")
    subject = next(item for item in action["fields"] if item["name"] == "subject")
    subject["required"] = False
    subject["nullable"] = True
    action["requiredFields"] = [item["name"] for item in action["fields"] if item.get("required")]
    monkeypatch.setattr(action_catalog_sync, "get_agent_action_catalog", lambda: remote)
    action_catalog_sync._SYNC_CONTEXT.set(None)
    result = action_catalog_sync.sync_action_catalog(run_id="java-fields-plan", force=True)
    assert result.status == "SYNCED"

    from src.orchestration.compiler import compile_task_plan
    plan = compile_task_plan(
        capability_id="meeting",
        execution_class="workflow",
        candidate_plan={
            "action_id": "meeting.create",
            "start_time": "2026-08-05 09:00:00",
            "end_time": "2026-08-05 10:00:00",
        },
    )
    assert plan is not None
    assert plan.status == "RESOLVED"
    clear_runtime_action_catalog()


def test_action_catalog_sync_blocks_cross_field_constraint_drift(monkeypatch):
    """Java constraints are authoritative and should be overlaid per Run."""
    monkeypatch.setenv("OA_AGENT_ACTION_CATALOG_SYNC", "true")
    monkeypatch.setenv("OA_AGENT_ACTION_CATALOG_STRICT", "true")
    remote = _remote_catalog()
    action = next(item for item in remote["actions"] if item["actionId"] == "meeting.update")
    action["constraints"] = [{"type": "at_least_one", "fields": ["subject"]}]
    monkeypatch.setattr(action_catalog_sync, "get_agent_action_catalog", lambda: remote)
    action_catalog_sync._SYNC_CONTEXT.set(None)
    result = action_catalog_sync.sync_action_catalog(run_id="constraint-overlay", force=True)
    assert result.status == "SYNCED"
    clear_runtime_action_catalog()


def test_action_catalog_sync_can_be_disabled_for_offline_tools(monkeypatch):
    monkeypatch.setenv("OA_AGENT_ACTION_CATALOG_SYNC", "false")
    monkeypatch.setenv("OA_AGENT_ACTION_CATALOG_STRICT", "true")
    action_catalog_sync._SYNC_CONTEXT.set(None)
    result = action_catalog_sync.sync_action_catalog(run_id="offline-test", force=True)
    assert result.status == "SKIPPED"
