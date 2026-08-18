from typing import Annotated, Any

from langchain.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from ..common import ToolResponse, bind_tool_call_id, emit, java_get, java_get_list, tool_failure, tool_success


_PARTY_FILE_FIELDS = (
    "id", "title", "categoryId", "categoryName", "summary", "content",
    "publishTime", "status", "readStatus",
)
_ATTACHMENT_FIELDS = ("id", "name", "size", "type")


def _safe_file_item(value: Any, *, include_content: bool) -> dict[str, Any]:
    """Keep the model/UI contract business-focused and storage-agnostic.

    The Java service remains the authority for visibility and attachment
    ownership.  In particular, raw file URLs, storage configuration, target
    audiences and read lists do not leave the business facade through a Tool
    result.  The browser fetches attachment bytes through its authenticated
    same-origin proxy instead.
    """
    raw = value if isinstance(value, dict) else {}
    item = {
        field: raw[field]
        for field in _PARTY_FILE_FIELDS
        if field in raw and (include_content or field != "content")
    }
    attachments = raw.get("attachments")
    if isinstance(attachments, list):
        item["attachments"] = [
            {
                field: attachment[field]
                for field in _ATTACHMENT_FIELDS
                if isinstance(attachment, dict) and field in attachment
            }
            for attachment in attachments
            if isinstance(attachment, dict)
        ]
    return item


def _safe_page(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    files = raw.get("list") if isinstance(raw.get("list"), list) else []
    total = raw.get("total")
    return {
        "total": total if isinstance(total, int) else len(files),
        "list": [_safe_file_item(item, include_content=False) for item in files],
    }


def _safe_detail(value: Any) -> dict[str, Any]:
    return _safe_file_item(value, include_content=True)


def _run(start_message: str, path: str, tool_name: str, params: dict[str, Any] | None = None, tool_call_id: str = "") -> ToolResponse:
    writer = get_stream_writer()
    emit(writer, "tool_started", start_message, toolName=tool_name, toolCallId=tool_call_id)
    try:
        return tool_success(java_get(path, params))
    except Exception as exc:
        emit(writer, "tool_failed", "党务文件查询失败，请稍后重试", toolName=tool_name, toolCallId=tool_call_id, errorCode="PARTY_FILE_FACADE_UNAVAILABLE")
        return tool_failure("PARTY_FILE_FACADE_UNAVAILABLE", "党务文件查询暂时不可用", details=str(exc))


@tool
def search_party_files(title: str = "", category_id: int | None = None, read_status: bool | None = None, page_no: int = 1, page_size: int = 10, tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """查询当前登录用户可见的党务文件，可按标题、分类和已读状态筛选。只读。"""
    params: dict[str, Any] = {"pageNo": max(page_no, 1), "pageSize": min(max(page_size, 1), 50)}
    if title.strip(): params["title"] = title.strip()
    if category_id is not None: params["categoryId"] = category_id
    if read_status is not None: params["readStatus"] = str(read_status).lower()
    bind_tool_call_id(tool_call_id)
    result = _run("📄 正在查询党务文件……", "/agent/tools/party-files/my-page", "search_party_files", params, tool_call_id)
    if not result.ok:
        return result
    data = _safe_page(result.data)
    presentation = {"blockType": "card", "cardType": "party_file", "view": "list"}
    emit(
        get_stream_writer(),
        "tool_completed",
        f"✅ 党务文件查询完成，共获取 {len(data['list'])} 条记录",
        toolName="search_party_files",
        toolCallId=tool_call_id,
        result=data,
        presentation=presentation,
    )
    return tool_success(data, presentation)


@tool
def get_party_file_detail(file_id: int, tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """获取当前登录用户可见的党务文件详情。调用后会记录当前用户已读。只读。"""
    bind_tool_call_id(tool_call_id)
    result = _run("📖 正在读取党务文件详情……", "/agent/tools/party-files/my-get", "get_party_file_detail", {"id": file_id}, tool_call_id)
    if not result.ok:
        return result
    data = _safe_detail(result.data)
    presentation = {"blockType": "card", "cardType": "party_file", "view": "detail"}
    emit(get_stream_writer(), "tool_completed", "✅ 党务文件详情读取完成", toolName="get_party_file_detail", toolCallId=tool_call_id, result=data, presentation=presentation)
    return tool_success(data, presentation)


@tool
def get_party_file_attachments(
    file_id: int,
    action: str = "inspect",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """核对已有党务文件附件；只读，不创建草稿，也不传输二进制内容。

    ``action`` is retained in the result for the UI contract. Preview/download
    bytes are exposed only by the authenticated browser proxy after the user
    clicks an attachment link.
    """
    action = str(action or "inspect").strip().lower() or "inspect"
    if action not in {"inspect", "preview", "download"}:
        action = "inspect"
    bind_tool_call_id(tool_call_id)
    result = _run(
        "📎 正在核对党务文件附件……",
        "/agent/tools/party-files/my-get",
        "get_party_file_attachments",
        {"id": file_id},
        tool_call_id,
    )
    if not result.ok:
        return result
    data = _safe_detail(result.data)
    attachments = data.get("attachments") if isinstance(data.get("attachments"), list) else []
    data["attachmentStatus"] = "AVAILABLE" if attachments else "NONE"
    data["attachmentCount"] = len(attachments)
    data["attachmentAction"] = action
    data["attachmentMessage"] = (
        "该文件包含可预览或下载的附件。"
        if attachments
        else "该文件没有附件。"
    )
    presentation = {"blockType": "card", "cardType": "party_file", "view": "attachments"}
    emit(
        get_stream_writer(),
        "tool_completed",
        "✅ 党务文件附件核对完成",
        toolName="get_party_file_attachments",
        toolCallId=tool_call_id,
        result=data,
        presentation=presentation,
    )
    return tool_success(data, presentation)


@tool
def get_party_file_attachment(file_id: int, attachment_id: int, action: str = "preview", tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """获取党务文件附件元数据并记录预览或下载动作；不会把二进制文件传给模型。只读。"""
    action = action.strip().lower() or "preview"
    if action not in {"preview", "download"}: action = "preview"
    bind_tool_call_id(tool_call_id)
    result = _run("📎 正在读取党务文件附件信息……", "/agent/tools/party-files/my-attachment", "get_party_file_attachment", {"id": file_id, "fileId": attachment_id, "action": action}, tool_call_id)
    if not result.ok:
        return result
    data = _safe_detail(result.data)
    presentation = {"blockType": "card", "cardType": "party_file", "view": "detail"}
    emit(get_stream_writer(), "tool_completed", "✅ 附件信息读取完成（未传输二进制内容）", toolName="get_party_file_attachment", toolCallId=tool_call_id, result=data, presentation=presentation)
    return tool_success(data, presentation)


@tool
def list_party_file_categories(tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """查询启用中的党务文件分类。只读。"""
    bind_tool_call_id(tool_call_id)
    writer = get_stream_writer()
    emit(writer, "tool_started", "正在查询党务文件分类……", toolName="list_party_file_categories", toolCallId=tool_call_id)
    try:
        result = tool_success(java_get_list("/agent/tools/party-files/categories"))
    except Exception as exc:
        emit(writer, "tool_failed", "党务文件分类查询失败，请稍后重试", toolName="list_party_file_categories", toolCallId=tool_call_id, errorCode="PARTY_FILE_FACADE_UNAVAILABLE")
        return tool_failure("PARTY_FILE_FACADE_UNAVAILABLE", "党务文件分类查询暂时不可用", details=str(exc))
    if result.ok: emit(get_stream_writer(), "tool_completed", "✅ 党务文件分类查询完成", toolName="list_party_file_categories", toolCallId=tool_call_id)
    return result
