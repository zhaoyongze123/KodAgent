"""Deterministic offline evaluator for the party approval golden dataset.

This is a contract/regression evaluator, not a replacement for the OA
authorization service. It validates that policy rules, case metadata and
golden assertions agree before the dataset is used to tune an Agent.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent-python"))
from src.services.party_approval_rules import evaluate_approval


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_golden(path: Path) -> dict[str, dict[str, Any]]:
    return {item["caseId"]: item for item in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())}


def evaluate_case(case: dict[str, Any], golden: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if case.get("expectedVerdict") != golden.get("expectedVerdict"):
        failures.append("verdict")
    if case.get("expectedCanSubmit") != golden.get("expectedCanSubmit"):
        failures.append("canSubmit")
    missing = set(case.get("missingAttachments") or case.get("expectedMissingMaterials") or [])
    expected_missing = set(golden.get("requiredMissingMaterials") or [])
    if not expected_missing.issubset(missing):
        failures.append("missingMaterials")
    related_rules = set(case.get("relatedRules") or [])
    required_rules = set(golden.get("requiredRuleIds") or [])
    if not required_rules.issubset(related_rules):
        failures.append("ruleIds")
    related_policies = set(case.get("relatedPolicies") or [])
    required_policies = set(golden.get("requiredMentionedPolicies") or [])
    if not required_policies.issubset(related_policies):
        failures.append("policies")
    if int(golden.get("minimumCitationCount") or 0) > 0 and not case.get("citation"):
        failures.append("citation")
    return failures


def evaluate_dataset(root: Path) -> dict[str, Any]:
    golden = load_golden(root / "golden" / "golden_assertions.jsonl")
    policies = [load_json(path) for path in sorted((root / "policies").glob("*/policy-*.rules.json"))]
    results = []
    for case_path in sorted((root / "approval_cases").glob("*/case.json")):
        case = load_json(case_path)
        case_id = case["caseId"]
        expected = golden.get(case_id, {})
        assessed = evaluate_approval(case, policies)
        failures = evaluate_case(case, expected)
        if assessed["verdict"] != expected.get("expectedVerdict"):
            failures.append("engineVerdict")
        if assessed["canSubmit"] != expected.get("expectedCanSubmit"):
            failures.append("engineCanSubmit")
        results.append({"caseId": case_id, "ok": not failures, "failures": failures, "assessed": assessed})
    passed = sum(item["ok"] for item in results)
    return {"total": len(results), "passed": passed, "failed": len(results) - passed, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate_dataset(args.root)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
