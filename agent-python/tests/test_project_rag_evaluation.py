from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


_MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "project_rag_evaluation.py"
_SPEC = importlib.util.spec_from_file_location("project_rag_evaluation", _MODULE_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
evaluate_project_rag = _MODULE.evaluate_project_rag


def _hit(file_id: str, chunk_id: str) -> dict[str, str]:
    return {
        "fileId": file_id,
        "chunkId": chunk_id,
        "citationId": f"资料 {file_id}",
        "name": f"资料-{file_id}.docx",
        "contentVersion": "v1",
        "section": "第 1 章",
    }


def _case(index: int, *, exact_name: bool = False, forbidden: list[str] | None = None) -> dict[str, object]:
    return {
        "id": f"case-{index}",
        "tags": ["exact_file_name"] if exact_name else [],
        "expectedEvidence": [{"fileId": f"file-{index}", "chunkId": f"chunk-{index}"}],
        "forbiddenFileIds": forbidden or [],
    }


class ProjectRagEvaluationTest(unittest.TestCase):
    def test_hybrid_gate_requires_real_recall_gain_without_filename_regression(self) -> None:
        cases = [_case(index, exact_name=index == 0) for index in range(40)]
        results: list[dict[str, object]] = []
        for index in range(40):
            correct = _hit(f"file-{index}", f"chunk-{index}")
            results.extend([
                {"id": f"case-{index}", "mode": "keyword", "elapsedMs": 9,
                 "hits": [correct] if index % 4 else []},
                {"id": f"case-{index}", "mode": "semantic", "elapsedMs": 11, "hits": [correct]},
                {"id": f"case-{index}", "mode": "hybrid", "elapsedMs": 13, "hits": [correct]},
            ])

        report = evaluate_project_rag(cases, results)

        self.assertEqual(1.0, report["modes"]["hybrid"]["recallAt5"])
        self.assertLess(report["modes"]["keyword"]["recallAt5"], report["modes"]["hybrid"]["recallAt5"])
        self.assertTrue(report["gate"]["eligible"])

    def test_hybrid_gate_blocks_permission_leakage_even_when_recall_is_higher(self) -> None:
        cases = [_case(index, forbidden=["restricted-file"] if index == 0 else None) for index in range(40)]
        results: list[dict[str, object]] = []
        for index in range(40):
            correct = _hit(f"file-{index}", f"chunk-{index}")
            hybrid_hits = [correct]
            if index == 0:
                hybrid_hits.append(_hit("restricted-file", "restricted-chunk"))
            results.extend([
                {"id": f"case-{index}", "mode": "keyword", "hits": [correct] if index % 4 else []},
                {"id": f"case-{index}", "mode": "semantic", "hits": [correct]},
                {"id": f"case-{index}", "mode": "hybrid", "hits": hybrid_hits},
            ])

        report = evaluate_project_rag(cases, results)

        self.assertEqual(1, report["modes"]["hybrid"]["permissionLeakCount"])
        self.assertFalse(report["gate"]["eligible"])
        self.assertIn("hybrid_permission_leakage", report["gate"]["reasons"])


if __name__ == "__main__":
    unittest.main()
