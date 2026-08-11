"""党务文件草稿的统一模型入口。"""

from __future__ import annotations

from typing import Annotated, Literal

from langchain.tools import InjectedToolCallId, tool
from pydantic import Field

from ..common import ToolResponse
from ..party_files.manage import _save_party_file_draft


@tool
def run_party_file_write_workflow(
    operation: Annotated[Literal["CREATE", "UPDATE", "DELETE"], Field(description="文件操作：CREATE 新建，UPDATE 修改，DELETE 删除。")],
    source_party_file_id: Annotated[int | None, Field(ge=1, description="要修改或删除的党务文件编号；UPDATE 和 DELETE 必填。")] = None,
    title: Annotated[str, Field(description="文件标题；CREATE 必填。")] = "",
    category_id: Annotated[int | None, Field(ge=1, description="文件分类编号；可由 category_name 解析。")] = None,
    category_name: Annotated[str, Field(description="文件分类名称；CREATE 时可代替 category_id。")] = "",
    summary: Annotated[str, Field(description="文件摘要。")] = "",
    content: Annotated[str, Field(description="文件正文；CREATE 必填。")] = "",
    attachment_file_ids: Annotated[str, Field(description="附件编号，多个编号以逗号分隔。")] = "",
    publish_time: Annotated[str, Field(description="计划发布时间。")] = "",
    targets: list[dict] | None = None,
    distribute_to_self: bool = False,
    storage_type: int | None = None,
    status: int | None = None,
    document_type: str = "",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """党务文件子 Agent 的唯一写入入口；只持久化待确认草稿。"""
    return _save_party_file_draft(
        operation, title, category_id, category_name, distribute_to_self, summary, content,
        attachment_file_ids, storage_type, status, publish_time, targets, source_party_file_id,
        tool_call_id, "run_party_file_write_workflow", document_type,
    )
