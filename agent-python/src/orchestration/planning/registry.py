"""Default domain compiler registry."""

from __future__ import annotations

from .approval import ApprovalPlanCompiler, ApprovalProcessPlanCompiler
from .contracts import PlanCompilerRegistry
from .party_file import PartyFilePlanCompiler
from .project import ProjectPlanCompiler
from .reports import ReportPlanCompiler
from .resources import ResourcePlanCompiler


def build_plan_compiler_registry() -> PlanCompilerRegistry:
    return PlanCompilerRegistry(
        (
            ApprovalPlanCompiler(),
            ApprovalProcessPlanCompiler(),
            PartyFilePlanCompiler(),
            ProjectPlanCompiler(),
            ResourcePlanCompiler("meeting"),
            ResourcePlanCompiler("schedule"),
            ReportPlanCompiler(),
        )
    )


__all__ = ["build_plan_compiler_registry"]
