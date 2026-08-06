"""Shared contracts for deterministic business workflows.

DeepAgents remains the parent orchestration shell, while fixed business
flows expose one small, typed contract at their boundary.  The registry uses
these contracts for discovery and runtime validation; workflow-specific
outcomes can still contain richer fields (for example the meeting booking
draft identifiers).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, TypeVar

from pydantic import BaseModel


SchemaType = type[BaseModel] | Mapping[str, Any] | None
Runner = Callable[..., Any]


@dataclass(frozen=True)
class ConfirmationPolicy:
    """How a workflow's side-effect boundary is presented to the caller."""

    required: bool = False
    tool_name: str | None = None
    card_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "required": self.required,
            "toolName": self.tool_name,
            "cardType": self.card_type,
        }


@dataclass(frozen=True)
class WorkflowContract:
    """Registry metadata and executable boundary for one workflow.

    ``input_schema`` and ``outcome_schema`` intentionally accept either a
    Pydantic model class or a pre-built JSON-schema mapping.  This keeps the
    registry independent from any particular workflow implementation while
    still allowing API/tool registration to expose a canonical schema.
    """

    workflow_type: str
    tool_name: str
    input_schema: SchemaType
    outcome_schema: SchemaType
    confirmation_policy: ConfirmationPolicy = field(default_factory=ConfirmationPolicy)
    feature_flag: str | None = None
    feature_flag_default: bool = False
    version: str = "1"
    runner: Runner | None = None
    description: str = ""

    def is_enabled(self, environ: Mapping[str, str] | None = None) -> bool:
        """Resolve the feature flag without duplicating routing policy."""
        if not self.feature_flag:
            return True
        import os

        values = environ if environ is not None else os.environ
        value = values.get(self.feature_flag)
        if value is None:
            return self.feature_flag_default
        return str(value).strip().lower() not in {"0", "false", "no", "off", "disabled"}

    @staticmethod
    def _schema(value: SchemaType) -> dict[str, Any] | None:
        if value is None:
            return None
        if isinstance(value, type) and issubclass(value, BaseModel):
            return value.model_json_schema()
        return dict(value)

    def metadata(self) -> dict[str, Any]:
        """Return the transport-safe, camelCase registry representation."""
        return {
            "workflowType": self.workflow_type,
            "toolName": self.tool_name,
            "inputSchema": self._schema(self.input_schema),
            "outcomeSchema": self._schema(self.outcome_schema),
            "confirmationPolicy": self.confirmation_policy.to_dict(),
            "featureFlag": self.feature_flag,
            "featureFlagDefault": self.feature_flag_default,
            "version": self.version,
            "description": self.description,
        }

    def run(self, **kwargs: Any) -> Any:
        if self.runner is None:
            raise RuntimeError(f"工作流 {self.workflow_type} 未配置执行器")
        return self.runner(**kwargs)


T = TypeVar("T")
