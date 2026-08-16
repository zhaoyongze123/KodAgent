"""通用文档附件工具。

模型负责决定文件标题、正文或工作簿结构；本工具只做输入边界校验并调用 Java
Artifact Service。它不识别任何业务报告类型，也不生成固定章节。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langchain.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from .events import emit
from .contracts import ToolResponse, tool_failure, tool_success
from .events import bind_tool_call_id
from .http_client import java_post


def _validate_workbook(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("workbook 必须是对象")
    sheets = value.get("sheets")
    if not isinstance(sheets, list) or not sheets:
        raise ValueError("XLSX 至少需要一个 sheets")
    if len(sheets) > 20:
        raise ValueError("工作簿最多支持 20 个工作表")
    normalized: list[dict[str, Any]] = []
    for sheet in sheets:
        if not isinstance(sheet, dict):
            raise ValueError("工作表必须是对象")
        name = str(sheet.get("name") or "Sheet1").strip()[:80]
        rows = sheet.get("rows")
        if not isinstance(rows, list) or len(rows) > 2000:
            raise ValueError("工作表行数无效或超过 2000 行")
        normalized_rows: list[list[Any]] = []
        for row in rows:
            if not isinstance(row, list) or len(row) > 100:
                raise ValueError("工作表列数无效或超过 100 列")
            normalized_rows.append([
                str(cell)[:5000] if cell is not None and not isinstance(cell, (int, float, bool)) else cell
                for cell in row
            ])
        normalized.append({"name": name or "Sheet1", "rows": normalized_rows})
    return {"sheets": normalized}


@tool
def create_document_artifact(
    title: str,
    format: Literal["DOCX", "XLSX"],
    content: str = "",
    workbook: dict[str, Any] | None = None,
    purpose: str = "",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """创建用户明确要求的可下载文档附件。

    DOCX 使用 content（支持 Markdown 标题/列表的纯文本）；XLSX 使用 workbook
    的 sheets/rows。内容必须来自当前回合已核验事实，工具不会替模型补写模板。
    """

    normalized_title = str(title or "").strip()
    normalized_format = str(format or "").strip().upper()
    if not normalized_title:
        return tool_failure("ARTIFACT_TITLE_REQUIRED", "附件标题不能为空")
    if normalized_format not in {"DOCX", "XLSX"}:
        return tool_failure("ARTIFACT_FORMAT_UNSUPPORTED", "当前仅支持 DOCX 和 XLSX")
    if len(normalized_title) > 200:
        return tool_failure("ARTIFACT_TITLE_TOO_LONG", "附件标题不能超过 200 个字符")
    normalized_content = str(content or "").replace("\x00", " ").strip()
    if len(normalized_content) > 100_000:
        return tool_failure("ARTIFACT_CONTENT_TOO_LARGE", "文档正文不能超过 100000 个字符")
    try:
        normalized_workbook = _validate_workbook(workbook)
    except ValueError as exc:
        return tool_failure("ARTIFACT_WORKBOOK_INVALID", str(exc))
    if normalized_format == "DOCX" and not normalized_content:
        return tool_failure("ARTIFACT_CONTENT_REQUIRED", "DOCX 正文不能为空")
    if normalized_format == "XLSX" and normalized_workbook is None:
        return tool_failure("ARTIFACT_WORKBOOK_REQUIRED", "XLSX 需要提供 workbook.sheets 数据")

    bind_tool_call_id(tool_call_id)
    writer = get_stream_writer()
    emit(writer, "tool_started", "正在制作文档附件", toolName="create_document_artifact", toolCallId=tool_call_id)
    try:
        result = java_post("/agent/artifacts", {
            "title": normalized_title,
            "format": normalized_format,
            "content": normalized_content,
            "workbook": normalized_workbook,
            "purpose": str(purpose or "").strip()[:500],
        })
        if not isinstance(result, dict):
            raise ValueError("附件服务返回了无效结果")
    except Exception as exc:
        emit(writer, "tool_failed", "附件制作失败", toolName="create_document_artifact", toolCallId=tool_call_id, errorCode="ARTIFACT_SERVICE_UNAVAILABLE")
        return tool_failure("ARTIFACT_SERVICE_UNAVAILABLE", "附件服务暂时不可用", details=str(exc))
    emit(writer, "tool_completed", "附件已生成", toolName="create_document_artifact", toolCallId=tool_call_id, result=result)
    return tool_success(result)


__all__ = ["create_document_artifact"]
