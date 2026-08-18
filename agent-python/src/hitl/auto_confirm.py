"""Configurable middleware shell for approval-card projection.

The projection algorithm lives in :mod:`hitl.projection`.  Domain modules
provide only their draft loader and argument builder through a callable; the
model-call lifecycle and sync/async parity are shared here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware


class ConfiguredApprovalProjectionMiddleware(AgentMiddleware):
    """Run one code-owned projection function for sync and async model calls."""

    def __init__(self, *, name: str, projector: Callable[[Any, Any], Any]) -> None:
        self.name = name
        self._projector = projector

    def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        return self._projector(request, handler(request))

    async def awrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        return self._projector(request, await handler(request))


__all__ = ["ConfiguredApprovalProjectionMiddleware"]
