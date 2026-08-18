"""Provider-neutral plan contracts.

Planning is a domain object, not a service implementation detail.  The model
creates ``CandidateTaskPlan``; only the compiler may create
``CompiledTaskPlan`` with an executable binding.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ExecutionClass = Literal[
    "metadata_query",
    "approval_query",
    "content_search",
    "document_understanding",
    "document_compare",
    "compliance_check",
    "report",
    "workflow",
    "fallback_react",
    "clarify",
]
PlanStatus = Literal["RESOLVED", "CLARIFY", "FALLBACK", "UNSUPPORTED"]


class CandidateTaskPlan(BaseModel):
    """Untrusted model output; it contains no tool name or business ID."""

    execution_class: ExecutionClass
    payload: dict[str, Any] = Field(default_factory=dict)


class CompiledTaskPlan(BaseModel):
    """Canonical plan persisted in the ToolMessage and used for dispatch."""

    plan_id: str
    status: PlanStatus
    capability_id: str
    execution_class: ExecutionClass
    execution_tool: str | None = None
    canonical: dict[str, Any] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    clarification_question: str | None = None


__all__ = ["CandidateTaskPlan", "CompiledTaskPlan", "ExecutionClass", "PlanStatus"]
