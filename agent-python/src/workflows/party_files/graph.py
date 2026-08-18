from __future__ import annotations

import difflib
import json
from typing import Any

from ...tools.common import invoke_tool
from ...tools.party_files.query import get_party_file_detail


def _data(value: Any) -> dict[str, Any]:
    if hasattr(value, "ok"):
        return value.data if value.ok and isinstance(value.data, dict) else {}
    if isinstance(value, dict):
        return value.get("data", value)
    if isinstance(value, str):
        try:
            return _data(json.loads(value))
        except json.JSONDecodeError:
            return {}
    return {}


def _load(file_id: int, call_id: str) -> dict[str, Any]:
    return _data(invoke_tool(get_party_file_detail, {
        "file_id": file_id,
        "tool_call_id": call_id,
    }))


def run_party_file_understanding_workflow(file_id: int, question: str = "", tool_call_id: str = "workflow", **_: Any) -> dict[str, Any]:
    """Load one authorized file and return bounded evidence for the parent Agent."""
    document = _load(int(file_id), f"{tool_call_id}:detail")
    content = str(document.get("content") or "")
    return {
        "status": "READY" if content else "FAILED",
        "question": question,
        "document": {key: document.get(key) for key in ("id", "title", "categoryName", "publishTime", "readStatus") if key in document},
        "content": content,
        "evidence": [{"documentId": document.get("id", file_id), "section": "全文", "quote": content[:12000]}] if content else [],
    }


def run_party_file_compare_workflow(left_file_id: int, right_file_id: int, tool_call_id: str = "workflow", **_: Any) -> dict[str, Any]:
    """Compare two authorized file versions with deterministic line-level diff."""
    left = _load(int(left_file_id), f"{tool_call_id}:left")
    right = _load(int(right_file_id), f"{tool_call_id}:right")
    left_lines = str(left.get("content") or "").splitlines()
    right_lines = str(right.get("content") or "").splitlines()
    diff = list(difflib.unified_diff(left_lines, right_lines, lineterm=""))
    added = [line[1:] for line in diff if line.startswith("+") and not line.startswith("+++")]
    removed = [line[1:] for line in diff if line.startswith("-") and not line.startswith("---")]
    return {"status": "READY" if left_lines and right_lines else "FAILED", "left": left, "right": right, "added": added[:200], "removed": removed[:200], "changedLineCount": len(added) + len(removed)}


def run_party_file_approval_check_workflow(task_id: str, file_id: int, tool_call_id: str = "workflow", **_: Any) -> dict[str, Any]:
    """Run the registered approval-vs-policy check through its Tool boundary."""
    # Keep the policy implementation in the existing tool module, but make
    # the registry runner point to the actual operation instead of silently
    # dispatching approval checks to the file-understanding workflow.
    from ...tools.workflows.party_files import check_approval_against_party_file

    result = invoke_tool(check_approval_against_party_file, {
        "task_id": task_id,
        "file_id": file_id,
        "tool_call_id": tool_call_id,
    })
    return _data(result)
