"""Canonical business-result presentation contract.

Tools own facts and permissions; the UI should not have to infer a card from
an arbitrary Markdown response.  This module defines the small, transport-safe
contract used by the result layer and adapts the legacy ``blockType`` /
``cardType`` dictionaries without breaking existing callers.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PresentationSpec(BaseModel):
    """The renderer-independent description of one primary business result.

    ``primaryResult`` is deliberately a flag rather than a copy of the data.
    The facts remain in ``ToolResponse.data`` and ``sourceResultId`` gives the
    client a stable identity for deduplication and updates.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    result_kind: str = Field(alias="resultKind")
    primary_result: bool = Field(default=True, alias="primaryResult")
    source_result_id: str = Field(alias="sourceResultId")
    result_group_id: str | None = Field(default=None, alias="resultGroupId")
    requested_scope: dict[str, Any] = Field(default_factory=dict, alias="requestedScope")
    observed_scope: dict[str, Any] = Field(default_factory=dict, alias="observedScope")
    summary: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    display_policy: dict[str, Any] = Field(default_factory=dict, alias="displayPolicy")


_CARD_KIND_MAP: dict[str, str] = {
    "todo": "record_list",
    "approval_inbox": "record_list",
    "approval_insights": "analysis",
    "approval_batch_preview": "workflow_draft",
    "approval_batch_result": "operation_result",
    "approval_template": "record_list",
    "approval_preview": "workflow_draft",
    "approval_submission": "operation_result",
    "approval_task": "record_detail",
    "approval_task_result": "operation_result",
    "approval_applications": "record_list",
    "approval_application": "record_detail",
    "approval_history": "record_list",
    "business_report": "analysis",
    "calendar": "record_list",
    "party_file": "record_detail",
    "party_file_knowledge": "document_answer",
    "meeting_booking": "workflow_draft",
    "meeting_draft": "workflow_draft",
    "error": "error",
}


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=True, exclude_none=True)
    return dict(value) if isinstance(value, Mapping) else {}


def _result_data(data: Any) -> Any:
    """Unwrap common ToolResponse/Java envelopes for metadata extraction."""
    if isinstance(data, BaseModel):
        data = data.model_dump(by_alias=True, exclude_none=True)
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (TypeError, ValueError, json.JSONDecodeError):
            return data
    if isinstance(data, Mapping) and "data" in data and "ok" in data:
        return data.get("data")
    return data


def _stable_source_result_id(data: Any, presentation: Mapping[str, Any]) -> str:
    explicit = presentation.get("sourceResultId") or presentation.get("source_result_id")
    if explicit:
        return str(explicit)
    value = _result_data(data)
    if isinstance(value, Mapping):
        for key in (
            "resultId", "result_id", "previewId", "preview_id", "draftId", "draft_id",
            "taskId", "task_id", "documentId", "document_id", "id",
        ):
            if value.get(key) not in (None, ""):
                return f"result:{value[key]}"
    # A content hash is only a correlation key.  It is not exposed as source
    # content and keeps retries/refreshes on the same result row.
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        encoded = repr(value)
    return "result:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _scope(value: Any, *, requested: bool) -> dict[str, Any]:
    value = _result_data(value)
    if not isinstance(value, Mapping):
        return {}
    key = "requestedScope" if requested else "observedScope"
    existing = value.get(key) or value.get("requested_scope" if requested else "observed_scope")
    if isinstance(existing, Mapping):
        return dict(existing)

    result: dict[str, Any] = {}
    if requested:
        for source, target in (
            ("sortBy", "sortBy"), ("sort_by", "sortBy"), ("limit", "limit"),
            ("pageSize", "pageSize"), ("page_size", "pageSize"),
            ("filters", "filters"), ("criteria", "criteria"),
        ):
            if source in value and value[source] is not None:
                result[target] = value[source]
    else:
        for source, target in (
            ("total", "totalCount"), ("totalCount", "totalCount"),
            ("returned", "returnedCount"), ("returnedCount", "returnedCount"),
            ("candidateCount", "candidateCount"), ("excludedCount", "excludedCount"),
            ("sortableCount", "sortableCount"), ("excludedNullCount", "excludedNullCount"),
            ("returnedCount", "returnedCount"), ("sortApplied", "sortApplied"),
            ("nullPolicy", "nullPolicy"),
        ):
            if source in value and value[source] is not None:
                result[target] = value[source]
        for key_name in ("items", "records", "candidates", "content", "results"):
            items = value.get(key_name)
            if isinstance(items, list):
                result.setdefault("returnedCount", len(items))
                break
    return result


def _summary(value: Any, presentation: Mapping[str, Any]) -> dict[str, Any]:
    candidate = presentation.get("summary")
    if isinstance(candidate, Mapping):
        result = dict(candidate)
    elif candidate:
        result = {"headline": str(candidate)}
    else:
        data = _result_data(value)
        result = {}
        if isinstance(data, Mapping):
            for key in ("headline", "summary", "message", "normalizedSummary"):
                if data.get(key) not in (None, ""):
                    if key == "summary" and isinstance(data[key], Mapping):
                        return dict(data[key])
                    result["headline"] = str(data[key])
                    break
    return result


def _default_display_policy(result_kind: str, observed_scope: Mapping[str, Any]) -> dict[str, Any]:
    total = observed_scope.get("totalCount")
    returned = observed_scope.get("returnedCount")
    has_more = isinstance(total, int) and isinstance(returned, int) and total > returned
    return {
        "defaultExpanded": result_kind not in {"analysis", "error"},
        "showRawDetails": False,
        "allowLoadMore": has_more,
    }


def normalize_presentation(
    presentation: PresentationSpec | Mapping[str, Any] | None,
    *,
    data: Any = None,
    result_kind: str | None = None,
    source_result_id: str | None = None,
    result_group_id: str | None = None,
    requested_scope: Mapping[str, Any] | None = None,
    observed_scope: Mapping[str, Any] | None = None,
    summary: Mapping[str, Any] | str | None = None,
    actions: list[Mapping[str, Any]] | None = None,
    display_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a canonical presentation dict while preserving legacy fields.

    Existing producers can continue sending ``{"blockType": "card",
    "cardType": "todo"}``.  New producers may provide any canonical field;
    explicit values always win over derived values.
    """
    original = _as_dict(presentation)
    card_type = str(original.get("cardType") or original.get("card_type") or "")
    kind = result_kind or original.get("resultKind") or original.get("result_kind")
    kind = str(kind or _CARD_KIND_MAP.get(card_type, "record_list"))
    observed = dict(observed_scope or original.get("observedScope") or original.get("observed_scope") or _scope(data, requested=False))
    requested = dict(requested_scope or original.get("requestedScope") or original.get("requested_scope") or _scope(data, requested=True))
    summary_value = _summary(data, original)
    if summary is not None:
        summary_value = dict(summary) if isinstance(summary, Mapping) else {"headline": str(summary)}
    action_values = actions if actions is not None else original.get("actions")
    normalized_actions = [dict(item) for item in action_values or [] if isinstance(item, Mapping)]
    policy = dict(display_policy or original.get("displayPolicy") or _default_display_policy(kind, observed))
    source_id = str(source_result_id or _stable_source_result_id(data, original))
    group_id = result_group_id or original.get("resultGroupId") or original.get("result_group_id")

    # Keep old keys in the output so existing renderers can roll forward
    # independently.  The canonical keys below are the only ones new clients
    # should use.
    result: dict[str, Any] = {
        **original,
        "resultKind": kind,
        "primaryResult": original.get("primaryResult", True),
        "sourceResultId": source_id,
        "resultGroupId": str(group_id) if group_id else None,
        "requestedScope": requested,
        "observedScope": observed,
        "summary": summary_value,
        "actions": normalized_actions,
        "displayPolicy": policy,
    }
    result.pop("result_kind", None)
    result.pop("primary_result", None)
    result.pop("source_result_id", None)
    result.pop("result_group_id", None)
    result.pop("requested_scope", None)
    result.pop("observed_scope", None)
    result.pop("display_policy", None)
    return PresentationSpec.model_validate(result).model_dump(by_alias=True, exclude_none=True)


def presentation_for_response(response: Any) -> Any:
    """Adapt a ToolResponse-like object without importing contracts eagerly."""
    from .contracts import ToolResponse

    if not isinstance(response, ToolResponse):
        return response
    if response.ok:
        if response.presentation is not None:
            presentation = response.presentation
            # Read-only approval tools often make overlapping calls for one
            # user request. Give the UI a durable group identity so it can
            # keep one primary result without merging independent domains.
            card_type = str(presentation.get("cardType", ""))
            if card_type in {"todo", "approval_inbox", "approval_insights", "approval_applications", "approval_application", "approval_history"} and not presentation.get("resultGroupId"):
                try:
                    from .events import current_agent_context

                    context = current_agent_context()
                    origin = context.get("originRunId") or context.get("runId")
                    message = context.get("messageId")
                    if origin and message:
                        presentation = {
                            **presentation,
                            "resultGroupId": f"approval-query:{origin}:{message}",
                        }
                except Exception:
                    pass
            response.presentation = normalize_presentation(presentation, data=response.data)
    else:
        error = response.error.model_dump() if response.error else {}
        response.presentation = normalize_presentation(
            response.presentation,
            data=error,
            result_kind="error",
            summary={"headline": error.get("message", "工具执行失败")},
        )
    return response
