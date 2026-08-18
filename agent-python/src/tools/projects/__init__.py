"""项目领域 Agent 工具包。

本包只负责把项目领域的已验证只读请求转发给 Java Project Provider；项目、任务、
成员、文件和权限的事实来源始终是 KodCloud project 插件及 Java 的权限复核结果。
Python 不直连 KodCloud 数据库，也不保存文件下载地址、会话令牌或文件正文。
"""

from .read import (
    analyze_project,
    get_project_activity,
    get_project_documents,
    get_project_snapshot,
    get_project_tasks,
    list_accessible_projects,
    search_project_knowledge,
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
