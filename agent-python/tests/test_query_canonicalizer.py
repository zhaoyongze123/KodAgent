from src.domain.query_plan import CandidateQueryIntent
from src.orchestration.query_canonicalizer import canonicalize_approval_query


def test_amount_rank_excludes_null_before_sort_and_limit():
    result = canonicalize_approval_query({
        "entity": "pending_approval",
        "operation": "rank",
        "sort": [{"field": "amount", "direction": "DESC"}],
        "limit": 10,
    })
    assert result.status == "RESOLVED"
    assert result.plan is not None
    assert result.plan.execution_order == ["filter", "sort", "limit"]
    assert result.plan.filters[0].model_dump() == {"field": "amount", "operator": "NOT_NULL", "value": None}
    assert result.plan.null_policy == "EXCLUDE"


def test_explicit_limit_then_sort_is_preserved_and_disclosed():
    result = canonicalize_approval_query({
        "entity": "pending_approval",
        "operation": "rank",
        "sort": [{"field": "amount", "direction": "DESC"}],
        "limit": 10,
        "explicit_order": ["limit", "sort"],
    })
    assert result.status == "RESOLVED"
    assert result.plan is not None
    assert result.plan.execution_order == ["limit", "sort"]
    assert "按用户明确要求先截取再排序" in result.plan.applied_policies


def test_ambiguous_order_requires_clarification():
    result = canonicalize_approval_query(CandidateQueryIntent(
        entity="pending_approval",
        operation="rank",
        sort=[{"field": "amount", "direction": "DESC"}],
        ambiguities=["用户同时表达了先取前十条和全量金额排序"],
    ))
    assert result.status == "CLARIFY"
    assert len(result.alternatives) == 2


def test_invalid_field_does_not_fallback_to_default_list():
    result = canonicalize_approval_query({
        "entity": "pending_approval",
        "operation": "filter",
        "filters": [{"field": "unknown", "operator": "EQ", "value": "x"}],
    })
    assert result.status == "INVALID"
    assert result.plan is None


def test_contradictory_amount_range_is_rejected():
    result = canonicalize_approval_query({
        "entity": "pending_approval",
        "operation": "filter",
        "filters": [
            {"field": "amount", "operator": "GT", "value": 100},
            {"field": "amount", "operator": "LT", "value": 50},
        ],
    })

    assert result.status == "INVALID"
    assert any("范围条件没有交集" in issue for issue in result.issues)


def test_conflicting_sort_direction_is_rejected():
    result = canonicalize_approval_query({
        "entity": "pending_approval",
        "operation": "rank",
        "sort": [
            {"field": "amount", "direction": "ASC"},
            {"field": "amount", "direction": "DESC"},
        ],
    })

    assert result.status == "INVALID"
    assert any("升序和降序" in issue for issue in result.issues)


def test_provider_compact_application_time_sort_alias_is_normalized():
    """Compact provider sort descriptors stay on the pending-inbox path."""
    result = canonicalize_approval_query({
        "operation": "QUERY",
        "limit": 3,
        "sort": [{"field": "applytime,desc", "direction": "DESC"}],
    })

    assert result.status == "RESOLVED"
    assert result.plan is not None
    assert result.plan.sort[0].model_dump() == {
        "field": "created_time", "direction": "DESC"
    }
