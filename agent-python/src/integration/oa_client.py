"""Typed entry point for calls to the Java OA Facade.

The low-level transport remains in ``tools.common.http_client`` for backwards
compatibility with existing tools and tests.  New business services should
depend on this object instead of importing the transport module directly.
That gives us one place to add tracing, tenant identity and request policy
without changing every domain tool.
"""

from __future__ import annotations

from typing import Any

from .java_facade import (
    JavaFacadeBusinessError,
    JavaFacadeConnectionError,
    JavaFacadeHttpError,
    JavaFacadeJsonDecodeError,
    JavaFacadeResponseTypeError,
    java_get,
    java_get_list,
    java_post,
    java_post_list,
)


class JavaFacadeClient:
    """Small, stateless facade client with an explicit identity boundary.

    The current transport resolves the active request identity from ContextVar
    state.  ``identity`` is provided for event/outbox workers that execute
    outside the original request context; it is never inferred from user text.
    """

    def __init__(self, *, identity: tuple[str, str] | None = None) -> None:
        self.identity = identity

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return java_get(path, params)

    def get_list(self, path: str, params: dict[str, Any] | None = None) -> list[Any]:
        return java_get_list(path, params)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return java_post(path, payload, identity=self.identity)

    def post_list(self, path: str, payload: dict[str, Any]) -> list[Any]:
        return java_post_list(path, payload, identity=self.identity)

    def close(self) -> None:
        """Compatibility hook for service lifecycles; transport is shared."""

    def __enter__(self) -> "JavaFacadeClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


__all__ = [
    "JavaFacadeBusinessError",
    "JavaFacadeClient",
    "JavaFacadeConnectionError",
    "JavaFacadeHttpError",
    "JavaFacadeJsonDecodeError",
    "JavaFacadeResponseTypeError",
]
