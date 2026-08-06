"""Stable LLM integration API.

The implementation is kept in the legacy module during the staged migration;
application and sub-agent construction code imports this boundary instead of
depending on the mixed ``services`` package.
"""

from ..services.model_runtime import (
    DynamicModelMiddleware,
    ModelRuntimeError,
    RunLifecycleMiddleware,
    resolve_run_model,
)

__all__ = ["DynamicModelMiddleware", "ModelRuntimeError", "RunLifecycleMiddleware", "resolve_run_model"]
