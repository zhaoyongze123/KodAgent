"""Conversation routing and working-memory models."""

from typing import Any, Literal

from pydantic import BaseModel, Field


ConversationMode = Literal[
    "chat",
    "follow_up",
    "fresh_query",
    "business_action",
    "image_generation",
    "workflow",
]

TaskComplexity = Literal["simple", "complex"]
ReasoningEffort = Literal["off", "low"]
RouteStrategy = Literal["direct", "delegate", "clarify", "fallback"]
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


class ConversationRoute(BaseModel):
    mode: ConversationMode
    # This is a runtime performance policy, not an authorization decision.
    # Business tools and confirmation boundaries remain independently guarded.
    task_complexity: TaskComplexity = "complex"
    reasoning_effort: ReasoningEffort = "low"
    # ``needs_tools`` means that tools may help the model answer.  It must not
    # by itself force a route_conversation retry after the model has already
    # produced a valid natural-language response.  Only requests with an
    # explicit structured-business contract set this flag, so writes and
    # recoverable field clarifications cannot silently bypass routing.
    requires_structured_route: bool = False
    needs_tools: bool = False
    needs_memory: bool = True
    needs_confirmation: bool = False
    show_progress: bool = False
    reason: str = ""
    target_task_id: str | None = None
    changed_fields: list[str] = Field(default_factory=list)
    task_candidates: list[dict[str, Any]] = Field(default_factory=list)
    capability_id: str = "general_agent"
    strategy: RouteStrategy = "fallback"
    # Domain capability and execution class are separate dimensions.  The
    # fast classifier does not choose this field; the capability/plan layer
    # may resolve it after validating the model proposal.
    execution_class: ExecutionClass | None = None
    confidence: float = 0.0
    missing_fields: list[str] = Field(default_factory=list)
    unsupported_criteria: list[str] = Field(default_factory=list)
