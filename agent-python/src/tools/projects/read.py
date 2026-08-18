"""项目领域的只读 Java Facade 工具。

文件职责
========
本文件是 Python Project Agent 与 Java Project Provider 的窄适配层。它只做输入
边界校验、用户可见的进度事件和结构化卡片投影；KodCloud 用户映射、项目成员
权限、``taskShowOnlySelf``、资料目录权限、统计口径、知识检索复核及报告导出均由
Java 确定性处理。

调用关系
========
``projects_agent -> 本文件工具 -> /agent/tools/projects -> Java Project Provider
-> KodCloud project agent bridge``。

所有工具只读。即使“生成报告”会在 Java 侧创建受控导出文件，也不会修改项目、
任务或资料；下载授权由 Java 按当前用户和短期链接另行校验。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from langchain.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from ..common import (
    ToolResponse,
    AGENT_TIMEZONE,
    bind_tool_call_id,
    emit,
    java_get,
    java_post,
    normalize_local_datetime,
    tool_failure,
    tool_success,
)


def _project_id(value: str | int) -> str:
    """规范化项目编号。

    参数：
        value：由路由计划或用户输入提供的项目编号。

    返回：去除两端空白后的编号；空编号返回空字符串，由各工具转成统一业务错误。
    """
    return str(value or "").strip()


def _page(value: int, *, default: int, maximum: int) -> int:
    """将分页参数限制在稳定、可预测的范围内。"""
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = default
    return min(maximum, max(1, normalized))


def _run_read(
    *,
    tool_name: str,
    start_message: str,
    completed_message: str,
    path: str,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    presentation: dict[str, Any],
    tool_call_id: str,
) -> ToolResponse:
    """调用一个项目只读接口并统一发布执行事件。

    参数：
        tool_name：Python 工具名，同时也是 Java 侧授权审计用的工具标识。
        start_message：调用前展示给用户的简短进度说明。
        completed_message：成功后展示给用户的简短结果说明。
        path：已经登记在 HTTP 路径白名单中的 Java 接口路径。
        params：GET 查询参数；与 ``payload`` 二选一。
        payload：POST 请求体；用于知识检索和报告生成。
        presentation：前端按卡片类型渲染的结构化展示信息。
        tool_call_id：LangGraph 注入的本次工具调用 ID。
    """
    bind_tool_call_id(tool_call_id)
    writer = get_stream_writer()
    emit(writer, "tool_started", start_message, toolName=tool_name, toolCallId=tool_call_id)
    try:
        result = java_post(path, payload or {}) if payload is not None else java_get(path, params)
        if not isinstance(result, dict):
            raise ValueError("项目服务返回了无效结果")
    except Exception as exc:
        emit(
            writer,
            "tool_failed",
            "项目数据服务暂不可用，请稍后重试",
            toolName=tool_name,
            toolCallId=tool_call_id,
            errorCode="PROJECT_FACADE_UNAVAILABLE",
        )
        return tool_failure("PROJECT_FACADE_UNAVAILABLE", "项目数据服务暂时不可用", details=str(exc))
    emit(
        writer,
        "tool_completed",
        completed_message,
        toolName=tool_name,
        toolCallId=tool_call_id,
        result=result,
        presentation=presentation,
    )
    return tool_success(result, presentation)


@tool
def list_accessible_projects(
    page_no: int = 1,
    page_size: int = 20,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """查询当前用户可访问的项目及本人角色。只读，不枚举无权限项目。"""
    page_no = _page(page_no, default=1, maximum=10_000)
    page_size = _page(page_size, default=20, maximum=100)
    return _run_read(
        tool_name="list_accessible_projects",
        start_message="正在查询可参与项目……",
        completed_message="已获取当前用户可访问的项目",
        path="/agent/tools/projects",
        params={"pageNo": page_no, "pageSize": page_size},
        presentation={"blockType": "card", "cardType": "project_list"},
        tool_call_id=tool_call_id,
    )


@tool
def get_project_snapshot(
    project_id: str,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """读取一个项目的基本信息、成员、配置、时间范围与资料同步状态。只读。"""
    project_id = _project_id(project_id)
    if not project_id:
        return tool_failure("PROJECT_ID_REQUIRED", "请先指定要查看的项目。")
    return _run_read(
        tool_name="get_project_snapshot",
        start_message="正在读取项目概览……",
        completed_message="项目概览读取完成",
        path=f"/agent/tools/projects/{project_id}/snapshot",
        presentation={"blockType": "card", "cardType": "project_snapshot", "projectId": project_id},
        tool_call_id=tool_call_id,
    )


@tool
def get_project_tasks(
    project_id: str,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """读取当前用户在指定项目中可见的任务树和任务字段。只读。"""
    project_id = _project_id(project_id)
    if not project_id:
        return tool_failure("PROJECT_ID_REQUIRED", "请先指定要查看任务的项目。")
    return _run_read(
        tool_name="get_project_tasks",
        start_message="正在读取项目任务……",
        completed_message="项目任务读取完成",
        path=f"/agent/tools/projects/{project_id}/tasks",
        presentation={"blockType": "card", "cardType": "project_tasks", "projectId": project_id},
        tool_call_id=tool_call_id,
    )


@tool
def get_project_activity(
    project_id: str,
    from_time: str = "",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """读取指定项目的项目/任务日志与最近活跃依据。只读。"""
    project_id = _project_id(project_id)
    if not project_id:
        return tool_failure("PROJECT_ID_REQUIRED", "请先指定要查看动态的项目。")
    params = None
    if isinstance(from_time, str) and from_time.strip():
        try:
            # Java Controller 的活动过滤契约使用 Unix 秒；模型和 Action Catalog
            # 对外仍使用统一的 yyyy-MM-dd HH:mm:ss，避免让模型处理时间戳。
            normalized = normalize_local_datetime(from_time)
            local_time = datetime.fromisoformat(normalized).replace(tzinfo=AGENT_TIMEZONE)
            params = {"fromTime": int(local_time.timestamp())}
        except (TypeError, ValueError):
            return tool_failure("PROJECT_ACTIVITY_TIME_INVALID", "动态起始时间格式无效，请使用 yyyy-MM-dd HH:mm:ss。")
    return _run_read(
        tool_name="get_project_activity",
        start_message="正在读取项目动态……",
        completed_message="项目动态读取完成",
        path=f"/agent/tools/projects/{project_id}/activity",
        params=params,
        presentation={"blockType": "card", "cardType": "project_activity", "projectId": project_id},
        tool_call_id=tool_call_id,
    )


@tool
def get_project_documents(
    project_id: str,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """读取项目资料目录中文件的元信息、版本、哈希与同步状态。只读。"""
    project_id = _project_id(project_id)
    if not project_id:
        return tool_failure("PROJECT_ID_REQUIRED", "请先指定要查看资料的项目。")
    return _run_read(
        tool_name="get_project_documents",
        start_message="正在读取项目资料目录……",
        completed_message="项目资料目录读取完成",
        path=f"/agent/tools/projects/{project_id}/documents",
        presentation={"blockType": "card", "cardType": "project_documents", "projectId": project_id},
        tool_call_id=tool_call_id,
    )


@tool
def analyze_project(
    project_id: str,
    user_question: str,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """读取 Java 确定性项目分析结果，作为自主调查的统计事实起点。

    参数：
        project_id：中央计划确定、且每次由 Java 重新校验权限的项目编号。
        user_question：用户原始问题，仅用于记录调查意图，不参与权限判断。
    """
    project_id = _project_id(project_id)
    if not project_id:
        return tool_failure("PROJECT_ID_REQUIRED", "请先指定要分析的项目。")
    if not isinstance(user_question, str) or not user_question.strip():
        return tool_failure("PROJECT_QUESTION_REQUIRED", "请说明要调查项目的具体问题。")
    return _run_read(
        tool_name="analyze_project",
        start_message="正在读取项目的确定性统计与风险事实……",
        completed_message="项目统计与风险事实读取完成",
        path=f"/agent/tools/projects/{project_id}/analysis",
        presentation={
            "blockType": "card", "cardType": "project_analysis", "projectId": project_id,
        },
        tool_call_id=tool_call_id,
    )


@tool
def search_project_knowledge(
    project_id: str,
    query: str,
    top_k: int = 5,
    include_policy_library: bool = True,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """检索有权限的项目资料，并可同时检索管理员维护的制度知识库。只读。"""
    project_id = _project_id(project_id)
    if not project_id:
        return tool_failure("PROJECT_ID_REQUIRED", "请先指定要检索资料的项目。")
    if not isinstance(query, str) or not query.strip():
        return tool_failure("PROJECT_KNOWLEDGE_QUERY_REQUIRED", "请输入要检索的项目资料问题或关键词。")
    return _run_read(
        tool_name="search_project_knowledge",
        start_message="正在检索项目资料与制度依据……",
        completed_message="已找到可引用的项目资料证据",
        path=f"/agent/tools/projects/{project_id}/knowledge/search",
        payload={
            "query": query.strip(),
            "topK": _page(top_k, default=5, maximum=20),
            "includePolicyLibrary": bool(include_policy_library),
        },
        presentation={"blockType": "card", "cardType": "project_knowledge", "projectId": project_id},
        tool_call_id=tool_call_id,
    )


__all__ = [
    "analyze_project",
    "get_project_activity",
    "get_project_documents",
    "get_project_snapshot",
    "get_project_tasks",
    "list_accessible_projects",
    "search_project_knowledge",
]
