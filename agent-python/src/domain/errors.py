"""Stable error taxonomy used across tools, workflows and the UI.

The human message is presentation.  ``kind`` and ``retryable`` are the
machine contract used by routing, recovery and the frontend, so callers do
not have to parse exception text or individual tool prefixes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ErrorKind = Literal[
    "validation",
    "authorization",
    "not_found",
    "conflict",
    "state",
    "dependency",
    "model",
    "internal",
]


@dataclass(frozen=True)
class ErrorDescriptor:
    code: str
    kind: ErrorKind
    retryable: bool = False
    user_action: str | None = None


def describe_error_code(code: str | None) -> ErrorDescriptor:
    """Map a legacy error code to the common machine-readable taxonomy."""
    normalized = str(code or "UNKNOWN_ERROR").strip().upper() or "UNKNOWN_ERROR"
    if normalized.startswith("MODEL_"):
        kind: ErrorKind = "model"
        retryable = normalized in {"MODEL_PROVIDER_UNAVAILABLE", "MODEL_TIMEOUT", "MODEL_RATE_LIMITED"}
    elif any(token in normalized for token in ("INVALID", "REQUIRED", "MISSING", "NEEDS_INPUT", "UNSUPPORTED")):
        kind: ErrorKind = "validation"
        retryable = False
    elif any(token in normalized for token in ("UNAUTHORIZED", "FORBIDDEN", "PERMISSION", "AUTH_", "IDENTITY", "HTTP_401", "HTTP_403")):
        kind = "authorization"
        retryable = False
    elif any(token in normalized for token in ("NOT_FOUND", "NO_DATA", "TASK_NOT_FOUND", "DRAFT_NOT_FOUND")):
        kind = "not_found"
        retryable = False
    elif any(token in normalized for token in ("CONFLICT", "COLLISION", "OVERLAP", "ALREADY_")):
        kind = "conflict"
        retryable = False
    elif any(token in normalized for token in ("STALE", "RESUME", "STATE", "ALREADY_COMPLETED", "EXPIRED")):
        kind = "state"
        retryable = False
    elif any(token in normalized for token in ("TIMEOUT", "UNAVAILABLE", "FACADE", "CONNECTION", "HTTP_408", "HTTP_425", "HTTP_429", "HTTP_500", "HTTP_502", "HTTP_503", "HTTP_504")):
        kind = "dependency"
        retryable = True
    else:
        kind = "internal"
        retryable = False
    return ErrorDescriptor(normalized, kind, retryable)


__all__ = ["ErrorDescriptor", "ErrorKind", "describe_error_code"]
