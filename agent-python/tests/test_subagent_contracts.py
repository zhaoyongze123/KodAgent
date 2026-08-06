import pytest

from src.subagents.contracts import validate_subagent_specs


class _Tool:
    def __init__(self, name):
        self.name = name


def _spec(name="approvals_agent"):
    return {
        "name": name,
        "description": "domain executor",
        "system_prompt": "prompt",
        "tools": [_Tool("report_progress")],
    }


def test_subagent_contracts_enrich_specs_with_boundary_metadata():
    result = validate_subagent_specs(
        [_spec("approvals_agent"), _spec("meeting_rooms_agent"), _spec("schedules_agent"), _spec("party_files_agent")]
    )
    contract = result[0]["contract"]
    assert contract["capabilityId"] == "approval_write"
    assert contract["writeBoundary"] == "draft_then_hitl"
    assert contract["toolNames"] == ["report_progress"]


def test_subagent_contracts_reject_duplicate_tools():
    spec = _spec()
    spec["tools"] = [_Tool("report_progress"), _Tool("report_progress")]
    with pytest.raises(RuntimeError, match="工具重复注册"):
        validate_subagent_specs([spec], required_names={"approvals_agent"})
