"""Shared human-in-the-loop primitives."""

"""HITL package boundary.

Concrete projection and state modules are intentionally lazy-imported.  HITL
services are imported while the Agent tool registry is being built; eager
imports here would create a cycle through middleware and domain services.
"""

__all__ = [
    "ConfiguredApprovalProjectionMiddleware", "project_confirmation_call",
]


def __getattr__(name: str):
    if name == "project_confirmation_call":
        from .projection import project_confirmation_call
        return project_confirmation_call
    if name == "ConfiguredApprovalProjectionMiddleware":
        from .auto_confirm import ConfiguredApprovalProjectionMiddleware
        return ConfiguredApprovalProjectionMiddleware
    raise AttributeError(name)
