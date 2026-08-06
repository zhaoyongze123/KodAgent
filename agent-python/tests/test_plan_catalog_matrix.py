from src.orchestration.capabilities import ACTION_SPECS, action_field_specs
from src.orchestration.compiler import compile_task_plan


def _value(field):
    if field.field_type == "array":
        return ["value"]
    if field.field_type in {"integer", "number"}:
        return 1
    if field.field_type == "boolean":
        return True
    if field.field_type == "datetime":
        return "2026-08-05 09:00:00"
    if field.field_type == "date":
        return "2026-08-05"
    if field.field_type == "object":
        return {}
    return "value"


def test_every_registered_action_has_a_compiler_result_and_no_tool_leakage():
    for action in ACTION_SPECS:
        payload = {field.name: _value(field) for field in action_field_specs(action) if field.required}
        authorized = [field.name for field in action_field_specs(action) if field.source_policy == "authorized_query_fact"]
        if authorized:
            payload["_authorized_source_fields"] = authorized
        payload.update({"action_id": action.action_id, "operation": action.operation})
        result = compile_task_plan(
            capability_id=action.capability_id,
            execution_class=action.execution_class,
            candidate_plan=payload,
        )
        assert result is not None, action.action_id
        assert result.capability_id == action.capability_id
        assert action.execution_tool not in result.canonical.values()
