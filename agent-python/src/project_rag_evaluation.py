"""项目资料混合 RAG 的离线评测契约。

评测器只读取人工标注的证据标识和已脱敏的检索结果，不访问 Java、KodCloud 或模型。
它不会保存用户问题或文件正文，因此可以作为灰度前的可重复质量门禁。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Mapping


RETRIEVAL_MODES = ("keyword", "semantic", "hybrid")
_CITATION_FIELDS = ("citationId", "fileId", "chunkId", "name", "contentVersion", "section")


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _values(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _case_evidence(case: Mapping[str, Any]) -> list[dict[str, str]]:
    evidence = [item for item in _values(case.get("expectedEvidence")) if isinstance(item, Mapping)]
    if evidence:
        return [{key: _text(value) for key, value in item.items() if _text(value)} for item in evidence]
    return [{"fileId": _text(file_id)} for file_id in _values(case.get("expectedFileIds")) if _text(file_id)]


def _matches(hit: Mapping[str, Any], expected: Mapping[str, str]) -> bool:
    for key in ("fileId", "chunkId", "contentVersion"):
        value = _text(expected.get(key))
        if value and _text(hit.get(key)) != value:
            return False
    return bool(_text(hit.get("fileId")))


def _mode_result(result_rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Mapping[str, Any]]]:
    grouped = {mode: {} for mode in RETRIEVAL_MODES}
    for row in result_rows:
        mode = _text(row.get("mode") or row.get("retrievalMode")).lower()
        case_id = _text(row.get("id") or row.get("caseId"))
        if mode in grouped and case_id:
            grouped[mode][case_id] = row
    return grouped


def _evaluate_mode(cases: list[Mapping[str, Any]], results: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    expected_cases = [case for case in cases if _case_evidence(case)]
    exact_cases = [case for case in expected_cases if "exact_file_name" in _values(case.get("tags"))]
    covered = 0
    retrieved = 0
    exact_retrieved = 0
    citation_total = 0
    citation_correct = 0
    permission_leak_case_ids: list[str] = []
    runtime_error_case_ids: list[str] = []
    elapsed_ms: list[float] = []
    missing_case_ids: list[str] = []

    for case in cases:
        case_id = _text(case.get("id"))
        result = results.get(case_id)
        if not result:
            missing_case_ids.append(case_id)
            continue
        covered += 1
        if _text(result.get("error") or result.get("failureCode")):
            runtime_error_case_ids.append(case_id)
        elapsed = result.get("elapsedMs", result.get("elapsed_ms"))
        if isinstance(elapsed, (int, float)) and elapsed >= 0:
            elapsed_ms.append(float(elapsed))
        hits = [item for item in _values(result.get("hits")) if isinstance(item, Mapping)]
        expected = _case_evidence(case)
        top_hits = hits[:5]
        if expected and any(any(_matches(hit, item) for item in expected) for hit in top_hits):
            retrieved += 1
            if "exact_file_name" in _values(case.get("tags")):
                exact_retrieved += 1
        for hit in top_hits:
            citation_total += 1
            complete = all(_text(hit.get(field)) for field in _CITATION_FIELDS)
            if complete and any(_matches(hit, item) for item in expected):
                citation_correct += 1
        forbidden = {_text(value) for value in _values(case.get("forbiddenFileIds")) if _text(value)}
        if forbidden and any(_text(hit.get("fileId")) in forbidden for hit in hits):
            permission_leak_case_ids.append(case_id)

    return {
        "caseCount": len(cases),
        "coverage": round(covered / len(cases), 4) if cases else 0.0,
        "missingCaseIds": missing_case_ids,
        "recallAt5": round(retrieved / len(expected_cases), 4) if expected_cases else 0.0,
        "exactFileNameRecallAt5": round(exact_retrieved / len(exact_cases), 4) if exact_cases else None,
        "citationAccuracyAt5": round(citation_correct / citation_total, 4) if citation_total else 0.0,
        "citationCountAt5": citation_total,
        "permissionLeakCount": len(permission_leak_case_ids),
        "permissionLeakCaseIds": permission_leak_case_ids,
        "runtimeErrorCount": len(runtime_error_case_ids),
        "runtimeErrorCaseIds": runtime_error_case_ids,
        "averageElapsedMs": round(mean(elapsed_ms), 2) if elapsed_ms else None,
    }


def _gate(modes: Mapping[str, Mapping[str, Any]], case_count: int) -> dict[str, Any]:
    reasons: list[str] = []
    if case_count < 40:
        reasons.append("case_count_below_40")
    for mode in RETRIEVAL_MODES:
        metrics = modes[mode]
        if metrics["coverage"] < 1.0:
            reasons.append(f"{mode}_incomplete")
        if metrics["permissionLeakCount"]:
            reasons.append(f"{mode}_permission_leakage")
        if metrics["runtimeErrorCount"]:
            reasons.append(f"{mode}_runtime_error")
    keyword = modes["keyword"]
    hybrid = modes["hybrid"]
    if hybrid["recallAt5"] <= keyword["recallAt5"]:
        reasons.append("hybrid_recall_not_improved")
    keyword_exact = keyword["exactFileNameRecallAt5"]
    hybrid_exact = hybrid["exactFileNameRecallAt5"]
    if keyword_exact is not None and hybrid_exact is not None and hybrid_exact < keyword_exact:
        reasons.append("hybrid_exact_filename_regressed")
    return {"eligible": not reasons, "reasons": reasons}


def evaluate_project_rag(
    cases: Iterable[Mapping[str, Any]], results: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """比较 keyword、semantic 和 hybrid 结果，并返回决定灰度的确定性报告。"""

    normalized_cases = [case for case in cases if isinstance(case, Mapping) and _text(case.get("id"))]
    grouped = _mode_result(row for row in results if isinstance(row, Mapping))
    modes = {mode: _evaluate_mode(normalized_cases, grouped[mode]) for mode in RETRIEVAL_MODES}
    return {
        "caseCount": len(normalized_cases),
        "modes": modes,
        "gate": _gate(modes, len(normalized_cases)),
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{number} must be a JSON object")
        rows.append(value)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate redacted project RAG retrieval results.")
    parser.add_argument("--cases", required=True, type=Path, help="annotated JSONL cases; do not commit raw document text")
    parser.add_argument("--results", required=True, type=Path, help="redacted JSONL results from each retrieval mode")
    parser.add_argument("--output", type=Path, help="optional JSON report path")
    parser.add_argument("--require-gate", action="store_true", help="return exit code 2 when hybrid cannot be enabled")
    args = parser.parse_args(argv)
    report = evaluate_project_rag(_read_jsonl(args.cases), _read_jsonl(args.results))
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0 if report["gate"]["eligible"] or not args.require_gate else 2


if __name__ == "__main__":
    raise SystemExit(main())
