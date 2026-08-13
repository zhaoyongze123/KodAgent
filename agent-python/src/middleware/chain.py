"""Declarative middleware order for the root Agent graph."""

from __future__ import annotations

from typing import Any

from ..runtime.model_runtime import DynamicModelMiddleware, RunLifecycleMiddleware
from ..orchestration.plan_projection import PlanToolProjectionMiddleware
from ..orchestration.phase_prompt import MainAgentPhasePromptMiddleware
from ..orchestration.conversation_context import ContextCandidateMiddleware
from ..orchestration.target_resolution import TargetResolutionMiddleware
from ..orchestration.policies import (
    CurrentUserMessageMiddleware,
    PendingPlanMiddleware,
    main_approval_tool_limit_middleware,
)
from .approval_batch_approval import ApprovalBatchAutoConfirmMiddleware
from .approval_request_approval import ApprovalRequestAutoConfirmMiddleware
from .approval_resume_gate import ApprovalResumeGateMiddleware
from .approval_task_approval import ApprovalTaskAutoConfirmMiddleware
from .duplicate_tool_message_guard import DuplicateToolMessageGuardMiddleware
from .meeting_approval import MeetingApprovalAutoConfirmMiddleware
from .meeting_approval_resume import MeetingApprovalResumeMiddleware
from .meeting_task_guard import MeetingTaskCallGuardMiddleware
from .personal_schedule_approval import PersonalScheduleApprovalArgsMiddleware
from .personal_schedule_approval_resume import PersonalScheduleApprovalResumeMiddleware
from .tool_audit import ToolAuditMiddleware
from .workflow_task_guard import DeterministicWorkflowTaskGuardMiddleware
from ..services.party_file_approval import PartyFileApprovalAutoConfirmMiddleware


class MiddlewareOrderError(RuntimeError):
    pass


def build_middleware_chain(*, dynamic_model: Any | None = None, phase_prompt: Any | None = None) -> list[Any]:
    """Build and validate the root chain in one place.

    The order is a contract: identity -> model/prompt -> route projection ->
    guards/audit -> draft projection -> resume.  Reordering a dependency now
    fails at startup instead of producing a missing card or duplicate write.
    """
    items = [
        CurrentUserMessageMiddleware(trusted_source=True),
        PendingPlanMiddleware(),
        # 候选只从 checkpoint 中已有的待办或授权查询结果生成，必须早于提示词注入。
        ContextCandidateMiddleware(),
        # 候选引用先完成 Java 定向核验；成功后本中间件写入代码二次编译的路由，
        # 让正常 PlanProjection 再派发真正写工作流，绝不直接复用候选 source ID。
        TargetResolutionMiddleware(),
        DuplicateToolMessageGuardMiddleware(),
        dynamic_model or DynamicModelMiddleware(),
        phase_prompt or MainAgentPhasePromptMiddleware(),
        PlanToolProjectionMiddleware(),
        RunLifecycleMiddleware(),
        MeetingTaskCallGuardMiddleware(),
        DeterministicWorkflowTaskGuardMiddleware(),
        ToolAuditMiddleware(),
        MeetingApprovalAutoConfirmMiddleware(),
        ApprovalBatchAutoConfirmMiddleware(),
        ApprovalTaskAutoConfirmMiddleware(),
        ApprovalRequestAutoConfirmMiddleware(),
        PartyFileApprovalAutoConfirmMiddleware(),
        PersonalScheduleApprovalArgsMiddleware(),
        ApprovalResumeGateMiddleware(),
        MeetingApprovalResumeMiddleware(),
        PersonalScheduleApprovalResumeMiddleware(),
        main_approval_tool_limit_middleware(),
    ]
    names = [str(getattr(item, "name", item.__class__.__name__)) for item in items]
    if len(names) != len(set(names)):
        raise MiddlewareOrderError(f"中间件名称重复: {names}")
    required_order = (
        ("CurrentUserMessageMiddleware", "PlanToolProjectionMiddleware"),
        ("CurrentUserMessageMiddleware", "PendingPlanMiddleware"),
        ("PendingPlanMiddleware", "ContextCandidateMiddleware"),
        ("ContextCandidateMiddleware", "TargetResolutionMiddleware"),
        ("TargetResolutionMiddleware", "PlanToolProjectionMiddleware"),
        ("ContextCandidateMiddleware", "MainAgentPhasePromptMiddleware"),
        ("PendingPlanMiddleware", "MainAgentPhasePromptMiddleware"),
        ("DynamicModelMiddleware", "MainAgentPhasePromptMiddleware"),
        ("PlanToolProjectionMiddleware", "MeetingTaskCallGuardMiddleware"),
        ("ToolAuditMiddleware", "MeetingApprovalAutoConfirmMiddleware"),
        ("MeetingApprovalAutoConfirmMiddleware", "MeetingApprovalResumeMiddleware"),
        ("ApprovalResumeGateMiddleware", "MeetingApprovalResumeMiddleware"),
        ("PersonalScheduleApprovalArgsMiddleware", "PersonalScheduleApprovalResumeMiddleware"),
    )
    positions = {name: index for index, name in enumerate(names)}
    for before, after in required_order:
        if before not in positions or after not in positions:
            raise MiddlewareOrderError(f"中间件链缺少依赖: {before} -> {after}")
        if positions[before] >= positions[after]:
            raise MiddlewareOrderError(f"中间件顺序无效: {before} 必须先于 {after}")
    return items


__all__ = ["MiddlewareOrderError", "build_middleware_chain"]
