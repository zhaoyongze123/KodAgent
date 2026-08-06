from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

from langchain.tools import InjectedToolCallId, tool

from ...tools.common import invoke_tool, tool_success
from ...tools.approval.actions import get_approval_task_detail
from ...workflows.party_files.graph import run_party_file_compare_workflow, run_party_file_understanding_workflow
from ...services.party_approval_rules import evaluate_approval


@tool
def run_party_file_understanding(file_id: int, question: str = "", tool_call_id: Annotated[str, InjectedToolCallId] = ""):
    """读取当前用户有权限的党务文件，返回带来源的内容证据给主 Agent。"""
    return tool_success(run_party_file_understanding_workflow(file_id=file_id, question=question, tool_call_id=tool_call_id), {"blockType": "card", "cardType": "party_file_knowledge"})


@tool
def run_party_file_compare(left_file_id: int, right_file_id: int, tool_call_id: Annotated[str, InjectedToolCallId] = ""):
    """比较两个当前用户有权限的党务文件版本，返回确定性差异。"""
    return tool_success(run_party_file_compare_workflow(left_file_id=left_file_id, right_file_id=right_file_id, tool_call_id=tool_call_id), {"blockType": "card", "cardType": "party_file_compare"})


@tool
def check_approval_against_party_file(task_id: str, file_id: int, tool_call_id: Annotated[str, InjectedToolCallId] = ""):
    """只读检查一条审批与制度文件中的材料要求是否匹配。"""
    approval = invoke_tool(get_approval_task_detail, {
        "task_id": task_id,
        "tool_call_id": f"{tool_call_id}:approval",
    })
    approval_data = approval.data if getattr(approval, "ok", False) else {}
    document = run_party_file_understanding_workflow(file_id=file_id, tool_call_id=f"{tool_call_id}:file")
    text = str(document.get("content") or "")
    requirements = [line.strip() for line in text.splitlines() if any(word in line for word in ("附件", "材料", "应当提交", "须提交", "必须提供"))]
    variables = approval_data.get("formVariables", {}) if isinstance(approval_data, dict) else {}
    rules_root = os.getenv("OA_AGENT_PARTY_APPROVAL_RULES_INDEX", "").strip()
    if rules_root and isinstance(variables, dict):
        policies = []
        for path in sorted(Path(rules_root).glob("policy-*.rules.json")):
            try:
                policies.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        if policies:
            case = dict(variables)
            case.setdefault("caseId", task_id)
            case.setdefault("providedAttachments", approval_data.get("providedAttachments", approval_data.get("attachments", [])))
            case.setdefault("missingAttachments", approval_data.get("missingAttachments", []))
            case.setdefault("approvalNodesPending", approval_data.get("approvalNodesPending", []))
            result = evaluate_approval(case, policies)
            result.update({"taskId": task_id, "document": document.get("document")})
            return tool_success(result, {"blockType": "card", "cardType": "party_file_compliance"})
    supplied = " ".join(str(value) for value in variables.values()) if isinstance(variables, dict) else ""
    checks = []
    missing = []
    for requirement in requirements[:50]:
        present = bool(supplied and any(token in supplied for token in requirement.split() if len(token) > 1))
        status = "PASS" if present else "MISSING"
        if not present:
            missing.append(requirement)
        checks.append({"requirement": requirement, "status": status, "evidence": "审批表单字段已包含相关内容" if present else "当前审批字段中未发现对应材料", "citation": {"documentId": document.get("document", {}).get("id", file_id), "section": "全文"}})
    if not variables:
        missing.append("未读取到可核验的审批表单字段")
        checks.append({"requirement": "审批表单字段", "status": "MISSING", "evidence": "未读取到表单字段", "citation": {"documentId": file_id, "section": "全文"}})
    verdict = "BLOCK" if missing else "PASS"
    return tool_success({"verdict": verdict, "checks": checks, "requirements": requirements[:50], "missingMaterials": missing, "canSubmit": verdict == "PASS", "document": document.get("document"), "taskId": task_id}, {"blockType": "card", "cardType": "party_file_compliance"})
