"""Ephemeral runtime context for deterministic workflow invocations.

Workflow state is checkpointed by LangGraph and must therefore contain only
serializable business data.  Stream writers are request-scoped callables, so
they live in this ContextVar for the duration of one graph invocation instead
of being added to graph state.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

from .runtime import WorkflowRuntime


_workflow_runtime: ContextVar[WorkflowRuntime | None] = ContextVar(
    "workflow_runtime",
    default=None,
)


def set_workflow_runtime(runtime: WorkflowRuntime) -> Token[WorkflowRuntime | None]:
    """Bind a runtime to the current synchronous or asynchronous call context."""
    return _workflow_runtime.set(runtime)


def get_workflow_runtime() -> WorkflowRuntime | None:
    """Return the current invocation's ephemeral runtime, if one is bound."""
    return _workflow_runtime.get()


def reset_workflow_runtime(token: Token[WorkflowRuntime | None]) -> None:
    """Restore the context that existed before a workflow invocation."""
    _workflow_runtime.reset(token)


__all__ = [
    "get_workflow_runtime",
    "reset_workflow_runtime",
    "set_workflow_runtime",
]
