"""项目领域只读计划编译器。

文件职责
========
把路由模型给出的 ``project.*`` 候选动作转换为只包含已登记字段的确定性计划。
简单查询绑定唯一 Python 工具；``project.investigate`` 绑定确定性分析入口，再由
项目子 Agent 在同一项目范围内使用安全只读 helper 自主补充任务、动态和资料事实。
这里不访问 Java、KodCloud 或数据库；项目权限、任务可见性和统计事实必须留在
Java Project Provider 中重新校验。

项目领域的所有一期动作都是只读：列表、项目快照、任务、动态、资料、知识检索和
报告导出。以后开放项目/任务写入时，必须另建工作流并接入 HITL，不能扩展本模块
绕过确认边界。
"""

from __future__ import annotations

import os
from typing import Any

from ...domain.plan import CompiledTaskPlan
from ..action_validation import authorized_source_fields, validate_action_payload
from ..capabilities import action_field_specs, resolve_action
from ..attachment_request import artifact_requested
from .common import plan_id, present
from .contracts import CompileContext


_PROJECT_EXECUTORS = {
    "project.list": "list_accessible_projects",
    "project.snapshot": "get_project_snapshot",
    "project.tasks": "get_project_tasks",
    "project.activity": "get_project_activity",
    "project.documents": "get_project_documents",
    "project.investigate": "analyze_project",
    "project.knowledge.search": "search_project_knowledge",
}

# ``project.investigate`` 一律先调用 analyze_project。下列范围只表示用户额外
# 明确提出的证据类型，编译器会从用户原话推导，模型不能通过 candidate_plan 自由
# 增删，避免报告导出被误当成资料、制度或动态调查已经完成。
_PROJECT_INVESTIGATION_SCOPE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("documents", ("资料", "材料", "文件", "文档", "附件", "资料目录")),
    (
        "knowledge",
        (
            "资料里", "资料中", "文件里", "文件中", "文档里", "文档中",
            "制度", "规范", "规定", "条款", "依据", "要求", "合规", "注意内容",
        ),
    ),
    ("tasks", ("任务明细", "任务列表", "全部任务", "所有任务", "逐项", "每项任务")),
    ("activity", ("项目动态", "动态记录", "操作日志", "更新记录", "最近更新", "最近有什么更新")),
)


def project_investigation_scopes(user_question: str) -> tuple[str, ...]:
    """从用户明确表述中推导项目调查必须覆盖的证据范围。

    这不是意图路由，也不产生新工具或权限。它只把“看资料”“依据制度要求”或
    “给出任务明细”等已说出口的子目标写入 canonical plan；领域 Agent 仍自主
    决定这些查询的顺序及是否补充其他只读事实。
    """

    question = str(user_question or "").strip()
    if not question:
        return ()
    return tuple(
        scope
        for scope, signals in _PROJECT_INVESTIGATION_SCOPE_RULES
        if any(signal in question for signal in signals)
    )


def _project_react_enabled() -> bool:
    """返回项目自主调查是否启用；默认开启，可由项目环境变量紧急回滚。"""
    return os.getenv("OA_AGENT_PROJECT_REACT", "true").strip().lower() in {"1", "true", "yes", "on"}


class ProjectPlanCompiler:
    """编译项目只读动作，并为自主调查签发不可越域的事实范围。"""

    capability_id = "project"

    def compile(self, context: CompileContext) -> CompiledTaskPlan | None:
        """将已选定的项目 Action 编译为不可携带额外参数的执行计划。

        参数：
            context：公共编译边界已规范化的候选计划与执行类别。

        返回：
            ``RESOLVED`` 时含项目动作的主执行器；调查动作随后只能使用执行契约
            声明的项目只读 helper。字段不完整时返回 ``CLARIFY``；其他项目动作
            返回 ``UNSUPPORTED``，禁止回退成跨领域任意工具调用。
        """
        if context.capability_id != self.capability_id:
            return None
        payload = dict(context.payload)
        action = resolve_action(
            self.capability_id,
            context.action_id or str(payload.get("action_id") or payload.get("actionId") or ""),
            str(payload.get("operation") or ""),
        )
        if action is None or action.action_id not in _PROJECT_EXECUTORS:
            canonical = {"operation": str(payload.get("operation") or "").strip().upper(), "version": "1"}
            return CompiledTaskPlan(
                plan_id=plan_id(self.capability_id, context.execution_class, canonical),
                status="UNSUPPORTED",
                capability_id=self.capability_id,
                execution_class=context.execution_class,
                canonical=canonical,
                issues=["项目领域动作未注册或尚未绑定只读执行器"],
            )
        if action.action_id == "project.investigate" and not _project_react_enabled():
            canonical = {"action_id": action.action_id, "operation": action.operation, "version": "1"}
            return CompiledTaskPlan(
                plan_id=plan_id(self.capability_id, action.execution_class, canonical),
                status="UNSUPPORTED",
                capability_id=self.capability_id,
                execution_class=action.execution_class,
                canonical=canonical,
                issues=["项目自主调查已由运维开关关闭"],
                clarification_question="项目自主调查当前不可用，请改为查询项目概览、任务或资料。",
            )
        if context.execution_class != action.execution_class:
            canonical = {"action_id": action.action_id, "operation": action.operation, "version": "1"}
            return CompiledTaskPlan(
                plan_id=plan_id(self.capability_id, action.execution_class, canonical),
                status="UNSUPPORTED",
                capability_id=self.capability_id,
                execution_class=context.execution_class,
                canonical=canonical,
                issues=["项目动作执行类别与注册契约不一致"],
            )
        validation = validate_action_payload(
            action,
            payload,
            authorized_source_fields=authorized_source_fields(payload),
        )
        canonical: dict[str, Any] = {
            "action_id": action.action_id,
            "operation": action.operation,
            "version": "1",
        }
        for field in action_field_specs(action):
            if present(payload.get(field.name)):
                canonical[field.name] = payload[field.name]
        if not validation.ok:
            return CompiledTaskPlan(
                plan_id=plan_id(self.capability_id, action.execution_class, canonical),
                status="CLARIFY",
                capability_id=self.capability_id,
                execution_class=action.execution_class,
                canonical=canonical,
                issues=validation.issues,
                missing_fields=validation.missing_fields,
                clarification_question="请补充要查询的项目及必要的检索或报告条件后继续。",
            )
        if action.action_id == "project.investigate":
            # 只从当前用户原话重新推导完成条件，不能相信模型 candidate_plan
            # 中伪造的 requested_scopes。
            canonical["requested_scopes"] = list(
                project_investigation_scopes(str(canonical.get("user_question") or ""))
            )
            # 附件交付是主 Agent 的通用能力，不属于项目调查计划。这个兼容字段只
            # 记录“用户是否明确要求文件”，不包含周报/分析报告等业务枚举，也不授予
            # 领域子 Agent 创建文件的权限。
            canonical["attachment_requested"] = artifact_requested(
                str(canonical.get("user_question") or "")
            )
        return CompiledTaskPlan(
            plan_id=plan_id(self.capability_id, action.execution_class, canonical),
            status="RESOLVED",
            capability_id=self.capability_id,
            execution_class=action.execution_class,
            execution_tool=_PROJECT_EXECUTORS[action.action_id],
            canonical=canonical,
        )


__all__ = ["ProjectPlanCompiler", "project_investigation_scopes"]
