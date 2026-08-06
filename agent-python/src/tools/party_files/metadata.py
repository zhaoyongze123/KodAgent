"""Deterministic execution for party-file metadata plans."""

from __future__ import annotations

import ast
import json
from typing import Annotated, Any

from langchain.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from ..common import ToolResponse, bind_tool_call_id, emit, java_post, tool_failure, tool_success


def _coerce_plan(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return None
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(value.strip())
        except (TypeError, ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            return dict(parsed)
    return None


@tool
def execute_party_file_metadata_plan(
    plan: dict[str, Any] | str,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """执行已编译的党务文件元数据查询计划；不读取正文、不调用向量检索。"""
    bind_tool_call_id(tool_call_id)
    plan = _coerce_plan(plan)
    if not isinstance(plan, dict) or plan.get("entity") != "party_file" or plan.get("operation") != "metadata_query":
        return tool_failure("PARTY_FILE_PLAN_INVALID", "党务文件元数据查询计划格式无效")
    writer = get_stream_writer()
    tool_name = "execute_party_file_metadata_plan"
    emit(writer, "tool_started", "📅 正在执行党务文件元数据查询计划……", toolName=tool_name, toolCallId=tool_call_id)
    try:
        # The Java facade is the permission and query fact source. Every
        # metadata plan uses this one authorized backend request.
        result = java_post("/agent/tools/party-files/query-plan", plan)
        if not isinstance(result, dict):
            raise ValueError("党务文件元数据查询返回了无效结果")
        matches = result.get("matches") if isinstance(result.get("matches"), list) else []
        result.setdefault("status", "READY" if matches else "NO_MATCH")
        result.setdefault("plan", plan)
        emit(writer, "tool_completed", f"✅ 已按查询计划完成党务文件筛选，共返回 {len(matches)} 条", toolName=tool_name, toolCallId=tool_call_id, result=result, presentation={"blockType": "card", "cardType": "party_file", "view": "list"})
        return tool_success(result, {"blockType": "card", "cardType": "party_file", "view": "list"})
    except (TypeError, ValueError) as exc:
        return tool_failure("PARTY_FILE_PLAN_INVALID", "党务文件元数据查询计划无法执行", details=str(exc))
    except Exception as exc:
        emit(writer, "tool_failed", "党务文件元数据查询失败，请稍后重试", toolName=tool_name, toolCallId=tool_call_id, errorCode="PARTY_FILE_FACADE_UNAVAILABLE")
        return tool_failure("PARTY_FILE_FACADE_UNAVAILABLE", "党务文件查询暂时不可用", details=str(exc))
    emit(writer, "tool_completed", f"✅ 已按查询计划完成党务文件筛选，共返回 {len(matches)} 条", toolName=tool_name, toolCallId=tool_call_id, result=result, presentation={"blockType": "card", "cardType": "party_file", "view": "list"})
    return tool_success(result, {"blockType": "card", "cardType": "party_file", "view": "list"})


__all__ = ["execute_party_file_metadata_plan"]
