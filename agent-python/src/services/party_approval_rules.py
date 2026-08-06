"""Deterministic evaluator for structured party approval policy rules."""
from __future__ import annotations

from typing import Any


def _facts(case: dict[str, Any]) -> dict[str, Any]:
    values = dict(case)
    values.update(case.get("scenarioData") or {})
    if "eventType" not in values and case.get("businessType") in {"EMERGENCY", "DISCIPLINE"}:
        values["eventType"] = case["businessType"]
    values["missingAttachment"] = set(case.get("missingAttachments") or [])
    values["providedAttachment"] = set(case.get("providedAttachments") or [])
    return values


def _condition_matches(condition: dict[str, Any], facts: dict[str, Any]) -> bool:
    field = condition.get("field")
    operator = str(condition.get("operator") or "EQUALS").upper()
    expected = condition.get("value")
    actual = facts.get(field)
    if operator == "EQUALS":
        if field == "missingAttachment":
            return expected in facts["missingAttachment"]
        return actual == expected
    if operator == "GTE":
        return actual is not None and actual >= expected
    if operator == "GT":
        return actual is not None and actual > expected
    if operator == "LT":
        return actual is not None and actual < expected
    if operator == "LTE":
        return actual is not None and actual <= expected
    if operator == "IN":
        return actual in (expected or [])
    if operator == "NOT_IN":
        return actual not in (expected or [])
    if operator == "OLDER_THAN":
        def version(value: Any) -> tuple[int, ...]:
            return tuple(int(part) for part in str(value or "v0").lstrip("v").split(".") if part.isdigit()) or (0,)
        return version(actual) < version(expected)
    return False


def evaluate_approval(case: dict[str, Any], policies: list[dict[str, Any]]) -> dict[str, Any]:
    facts = _facts(case)
    related = set(case.get("relatedRules") or [])
    applicable = []
    for policy in policies:
        for rule in policy.get("rules", []):
            if related and rule.get("ruleId") not in related:
                continue
            conditions = rule.get("conditions") or []
            if all(_condition_matches(item, facts) for item in conditions):
                applicable.append((policy, rule))
    provided = facts["providedAttachment"]
    # OA's pending-node list is authoritative. Absence from completed nodes is
    # not itself a violation because a node may be outside this process.
    pending_nodes = set(case.get("approvalNodesPending") or [])
    aliases = {
        "党委会前置研究意见": {"党委会前置研究意见", "党委会会议纪要", "党委会议纪要"},
        "大额资金支付审批表": {"大额资金支付审批表", "付款申请单"},
        "风险评估报告": {"风险评估报告", "立项评审意见"},
        "第三方评估意见": {"第三方评估意见", "立项评审意见"},
    }
    missing_materials: list[str] = []
    missing_nodes: list[str] = []
    checks = []
    citations = []
    verdict = "PASS"
    for policy, rule in applicable:
        required = rule.get("requiredAttachments") or []
        nodes = rule.get("requiredApprovalNodes") or []
        # Payment controls only apply to payment forms; investment cases may
        # cite the cross-domain rule but do not inherit payment attachments.
        if policy.get("documentId") == "policy-004" and facts.get("businessType") != "PAYMENT":
            required = []
            nodes = []
        for material in required:
            accepted = aliases.get(material, {material})
            if not accepted.intersection(provided) and material not in missing_materials:
                missing_materials.append(material)
        for node in nodes:
            if node in pending_nodes and node not in missing_nodes:
                missing_nodes.append(node)
        missing = [item for item in required if not aliases.get(item, {item}).intersection(provided)]
        pending = [item for item in nodes if item in pending_nodes]
        condition_violation = any(str(c.get("field")) in {"policyStatus", "policyVersion", "department", "missingCriticalAttachment", "missingOptionalAttachment", "attachmentTypeMismatch", "attachmentEmpty", "attachmentOutdated", "skipMandatoryNode"} for c in (rule.get("conditions") or []))
        if facts.get("meetingType") == "PARTY_COMMITTEE" and facts.get("attendeeRatio") is not None and facts["attendeeRatio"] < 2 / 3:
            condition_violation = True
        checks.append({"ruleId": rule.get("ruleId"), "article": rule.get("article"), "status": "MISSING" if missing or pending or condition_violation else "PASS", "missingMaterials": missing, "missingNodes": pending, "citationText": rule.get("citationText")})
        citations.append({"policyId": policy.get("documentId"), "ruleId": rule.get("ruleId"), "article": rule.get("article"), "quote": rule.get("citationText")})
        if missing or pending or condition_violation:
            rule_verdict = str(rule.get("missingMaterialVerdict") or "WARN").upper()
            if rule_verdict == "BLOCK":
                verdict = "BLOCK"
            elif verdict != "BLOCK":
                verdict = "WARN"
    return {"verdict": verdict, "canSubmit": verdict != "BLOCK", "applicableRuleIds": [rule.get("ruleId") for _, rule in applicable], "checks": checks, "missingMaterials": missing_materials, "missingApprovalNodes": missing_nodes, "citations": citations}
