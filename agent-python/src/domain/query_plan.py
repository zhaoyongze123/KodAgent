"""Provider-neutral query intent and canonical execution contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


QueryOperation = Literal["list", "filter", "rank", "analyze"]
ResolutionStatus = Literal["RESOLVED", "CLARIFY", "INVALID", "UNSUPPORTED"]
SortDirection = Literal["ASC", "DESC"]


class QueryFilter(BaseModel):
    field: str
    operator: str
    value: Any = None


class QuerySort(BaseModel):
    field: str
    direction: SortDirection


class CandidateQueryIntent(BaseModel):
    """Model-produced intent. It contains no business IDs and executes nothing."""

    entity: str
    operation: QueryOperation = "list"
    filters: list[QueryFilter] = Field(default_factory=list)
    sort: list[QuerySort] = Field(default_factory=list)
    limit: int | None = None
    explicit_order: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)


# Orchestration code uses the shorter names when it does not need to expose
# that the object is untrusted model output.  Keep one model as the source of
# truth so aliases cannot drift.
CandidateIntent = CandidateQueryIntent
QueryIntent = CandidateQueryIntent


class CanonicalQueryPlan(BaseModel):
    entity: str
    operation: QueryOperation
    filters: list[QueryFilter] = Field(default_factory=list)
    sort: list[QuerySort] = Field(default_factory=list)
    limit: int = 20
    null_policy: Literal["EXCLUDE", "LAST", "FIRST", "NOT_APPLICABLE"] = "NOT_APPLICABLE"
    execution_order: list[str] = Field(default_factory=list)
    requested_scope: dict[str, Any] = Field(default_factory=dict)
    applied_policies: list[str] = Field(default_factory=list)


class ResolutionResult(BaseModel):
    status: ResolutionStatus
    original_intent: CandidateQueryIntent
    plan: CanonicalQueryPlan | None = None
    issues: list[str] = Field(default_factory=list)
    clarification_question: str | None = None
    alternatives: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def canonical_plan(self) -> CanonicalQueryPlan | None:
        """Compatibility accessor for the generic orchestration contract."""

        return self.plan

    @property
    def missing_fields(self) -> list[str]:
        return [issue for issue in self.issues if "缺少" in issue]

    @property
    def unsupported_fields(self) -> list[str]:
        return [issue for issue in self.issues if "不支持" in issue]
