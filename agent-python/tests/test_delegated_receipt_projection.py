from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from src.orchestration.conversation_context import _model_visible_tool_data
    from src.orchestration.delegated_receipt import (
        DelegatedProjectInvestigationReceipt,
        _project_analysis_model_facts,
    )
    _IMPORT_ERROR: ModuleNotFoundError | None = None
except ModuleNotFoundError as error:  # Optional runtime extras are absent in lightweight CI.
    _IMPORT_ERROR = error


@unittest.skipIf(_IMPORT_ERROR is not None, f"agent runtime extras unavailable: {_IMPORT_ERROR}")
class DelegatedReceiptProjectionTest(unittest.TestCase):
    def test_project_citation_projects_limited_excerpt_contract(self) -> None:
        receipt = DelegatedProjectInvestigationReceipt.model_validate(
            {
                "planId": "plan-1",
                "projectId": "project-1",
                "status": "SUCCEEDED",
                "toolTrace": [{"tool": "search_project_knowledge", "status": "SUCCEEDED"}],
                "facts": {
                    "analyze_project": [
                        {"project": {"name": "滨江片区规划"}, "kpis": {"total": 3}}
                    ]
                },
                "citations": [
                    {
                        "citationId": "资料 1",
                        "sourceType": "PROJECT_FILES",
                        "name": "任务书.docx",
                        "section": "第 1 章",
                        "contentVersion": "v2",
                        "retrievalMethod": "hybrid",
                        "excerpt": "受限摘录",
                        "chunkId": 9,
                        "fileId": 18,
                    }
                ],
            }
        )

        citations = _project_analysis_model_facts(receipt)["knowledge"]["citations"]

        self.assertEqual("资料 1", citations[0]["citationId"])
        self.assertEqual("受限摘录", citations[0]["excerpt"])
        self.assertNotIn("content", citations[0])
        self.assertNotIn("chunkId", citations[0])
        self.assertNotIn("fileId", citations[0])

    def test_model_visible_tool_data_hides_rag_internal_sorting_fields(self) -> None:
        visible = _model_visible_tool_data(
            {
                "ok": True,
                "citationId": "资料 1",
                "excerpt": "受限摘录",
                "chunkId": 9,
                "projectId": 101,
                "fusionScore": 0.1,
                "matchedTerms": ["进度"],
            }
        )

        self.assertEqual("资料 1", visible["citationId"])
        self.assertNotIn("chunkId", visible)
        self.assertNotIn("projectId", visible)
        self.assertNotIn("fusionScore", visible)
        self.assertNotIn("matchedTerms", visible)


if __name__ == "__main__":
    unittest.main()
