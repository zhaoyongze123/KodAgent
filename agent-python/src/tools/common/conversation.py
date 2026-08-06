"""Conversation tools that do not call business systems."""

import ast
import json
import re
from typing import Any, Literal

from langchain.tools import tool
from pydantic import BaseModel, Field, field_validator

from ...domain.conversation import ExecutionClass, RouteStrategy
from ...orchestration.routing.router import classify_message, set_route_reasoning_policy
from ...orchestration.routing.recovery import (
    party_file_attachment_plan,
    party_metadata_fallback_plan,
    recover_party_file_write_candidate,
    recover_party_file_write_intent,
    schedule_metadata_fallback_plan,
)
from ...orchestration.capabilities import (
    APPROVAL_PROCESS_CAPABILITY_ID,
    action_catalog_prompt,
    action_description,
    action_execution_class,
    action_field_specs,
    action_required_fields,
    action_read_only,
    action_requires_confirmation,
    actions_for_capability,
    capability_routing_enabled,
    resolve_action,
    resolve_capability,
)
from ...orchestration.query_canonicalizer import canonicalize_approval_query
from ...orchestration.action_selection import (
    recover_approval_process_action,
    recover_approval_read_action,
)
from ...orchestration.compiler import compile_plan
from ...orchestration.planning.party_file import normalize_party_file_operation
from ...orchestration.planning.resources import infer_workflow_capability
from .events import emit
from langgraph.config import get_stream_writer
from .contracts import ToolResponse, tool_failure, tool_success

class RouteConversationInput(BaseModel):
    """Typed boundary for the two-stage route tool.

    ``capability_id`` is required at both stages.  The first stage chooses a
    registered domain (or ``general_agent`` when genuinely unknown); the
    second stage keeps that same domain and adds ``action_id`` and payload.
    Making the domain required prevents a provider from silently omitting the
    only fact that distinguishes a deterministic business plan from a generic
    ReAct fallback.
    """

    message: str
    task_complexity: Literal["simple", "complex"] = "simple"
    capability_id: str = Field(
        ...,
        description="第一阶段选择的能力域；未知请求必须传 general_agent，不能省略。",
    )
    action_id: str | None = None
    strategy: RouteStrategy | None = None
    confidence: float | None = None
    missing_fields: list[str] | None = None
    unsupported_criteria: list[str] | None = None
    query_intent: dict | str | None = None
    execution_class: ExecutionClass | None = None
    candidate_plan: dict[str, Any] | str | None = None

    @field_validator("missing_fields", "unsupported_criteria", mode="before")
    @classmethod
    def _coerce_string_lists(cls, value: Any) -> Any:
        """Accept JSON-string lists from providers while preserving the schema."""
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return [text]
        return parsed if isinstance(parsed, list) else [str(parsed)]


def _coerce_object(value: Any) -> dict[str, Any] | None:
    """Normalize provider tool arguments without moving routing into prose.

    A few OpenAI-compatible tool-call adapters serialize an object argument as
    a JSON string.  The route contract is still the same typed object; this
    adapter only repairs the transport representation and rejects arbitrary
    text.  ``ast.literal_eval`` is limited to literals and supports providers
    that emit Python-style single-quoted dictionaries.
    """
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
        except (TypeError, ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            return dict(parsed)
    return None


def _suggest_action_id_from_payload(
    capability_id: str | None,
    candidate_plan: dict[str, Any] | None,
    query_intent: dict[str, Any] | None,
) -> str | None:
    """Suggest an action using the registered field schema only.

    This is a presentation aid for the second routing stage, not a prose
    classifier.  If the provider already extracted a field that exists in
    exactly one action in the selected domain (for example ``limit`` in the
    pending-approval query), expose that action as a hint while still
    requiring the provider to submit the registered ``action_id``.
    """
    payload = {
        **(query_intent if isinstance(query_intent, dict) else {}),
        **(candidate_plan if isinstance(candidate_plan, dict) else {}),
    }
    ignored = {
        "action_id", "actionId", "operation", "action", "entity", "type",
        "domain", "execution_class", "executionClass", "_authorized_source_fields",
        "_action_id_synthesized",
    }
    supplied = {str(key) for key, value in payload.items() if key not in ignored and value not in (None, "", [], {})}
    if not supplied:
        return None
    matches: list[tuple[str, int]] = []
    for action in actions_for_capability(capability_id):
        names = {field.name for field in action_field_specs(action)}
        overlap = supplied & names
        # An action can accept the supplied typed fields only when every
        # field is in its schema.  At least one overlap makes the hint
        # meaningful; otherwise a domain-level payload remains ambiguous.
        if overlap and supplied <= names:
            matches.append((action.action_id, len(overlap)))
    if not matches:
        return None
    best_score = max(score for _, score in matches)
    best = [action_id for action_id, score in matches if score == best_score]
    return best[0] if len(best) == 1 else None


def _infer_typed_action_from_shape(
    capability_id: str | None,
    execution_class: str | None,
    candidate_plan: dict[str, Any] | None,
    query_intent: dict[str, Any] | None,
    message: str = "",
) -> tuple[str, str, str] | None:
    """Recover a domain/action only from an explicit typed payload shape.

    This is intentionally narrower than the removed operation-only fallback:
    a bare ``QUERY`` or ``CREATE`` remains unsupported.  The payload must
    contain an entity or fields that uniquely identify one registered action.
    """
    candidate = candidate_plan if isinstance(candidate_plan, dict) else {}
    intent = query_intent if isinstance(query_intent, dict) else {}
    entity = str(
        candidate.get("entity") or candidate.get("type") or candidate.get("object_type")
        or candidate.get("objectType") or intent.get("entity") or intent.get("type") or ""
    ).strip().lower().replace("-", "_")
    operation = str(
        candidate.get("operation") or candidate.get("action")
        or intent.get("operation") or intent.get("action") or ""
    ).strip().upper().replace("-", "_")
    if capability_id and capability_id not in {"", "general", "general_agent"}:
        domain = str(capability_id).strip().lower().replace("-", "_")
    elif entity in {"my_requests", "my_applications", "approval_applications"} and re.search(
        r"我发起|我的申请|发起的审批|申请记录", str(message or "")
    ):
        return "approval_process", "approval.process.applications", "approval_query"
    elif entity in {
        "pending_approval", "approval", "approval_task", "approvals", "todo",
        "pending", "pending_approvals", "my_pending", "my_requests", "my_approvals",
    }:
        # ``my_requests`` is a provider alias that is ambiguous in isolation.
        # In the absence of explicit “我发起/我的申请” wording, the OA
        # product's short “找审批” query means the user's pending inbox.
        domain = "approval_read"
        entity = "pending_approval"
    elif entity in {"meeting", "meeting_booking", "meeting_room", "room_booking"}:
        domain = "meeting"
    elif entity in {"schedule", "personal_schedule", "calendar"}:
        domain = "schedule"
    elif entity in {"party_file", "party_files", "partyfile", "party_document"}:
        domain = "party_file"
    else:
        sort_values = candidate.get("sort") or intent.get("sort") or []
        # A few providers encode a typed approval ranking as
        # ``order_by="create_time desc"`` instead of the registered ``sort``
        # array.  Treat only known approval sort fields as the compatibility
        # signal; an arbitrary ``limit`` or generic CRUD verb remains
        # ambiguous and still falls back to the normal domain planner.
        raw_order = candidate.get("order_by") or candidate.get("orderBy") or intent.get("order_by") or intent.get("orderBy")
        if raw_order and not sort_values:
            sort_values = [raw_order] if isinstance(raw_order, str) else raw_order
        if isinstance(sort_values, str):
            sort_values = [sort_values]
        sort_fields = {
            str(
                item.get("field") if isinstance(item, dict) else str(item).split()[0]
            ).lower().replace("createtime", "created_time")
            for item in sort_values
        }
        if (
            sort_fields & {"amount", "created_time", "create_time", "process_type", "pending_days", "processdefinitionname"}
            or (
                sort_fields & {"recent", "latest", "newest"}
                and re.search(r"审批|待办|流程", str(message or ""))
            )
        ):
            domain = "approval_read"
        elif sort_fields & {"publishtime", "publish_time", "title", "categoryname"}:
            domain = "party_file"
        elif any(key in candidate or key in intent for key in ("start_time", "end_time", "source_booking_id")):
            domain = "meeting" if "booking" in entity or "meeting" in entity else "schedule"
        else:
            return None
    if domain == "approval_read":
        has_approval_shape = (
            entity in {"pending_approval", "approval", "approval_task", "approvals"}
            or operation in {"QUERY", "LIST", "SEARCH", "RANK", "FILTER", "ANALYZE"}
            or bool(candidate.get("sort") or candidate.get("filters") or candidate.get("limit") is not None
                    or intent.get("sort") or intent.get("filters") or intent.get("limit") is not None)
        )
        if not has_approval_shape:
            return None
        return domain, "approval.read.pending", "metadata_query"
    if domain == "meeting" and operation in {"BOOK", "CREATE", "CREATE_DRAFT", "UPDATE", "CANCEL", "DELETE"}:
        action = {"BOOK": "meeting.create", "CREATE": "meeting.create", "CREATE_DRAFT": "meeting.create",
                  "UPDATE": "meeting.update", "CANCEL": "meeting.cancel", "DELETE": "meeting.cancel"}[operation]
        return domain, action, "workflow"
    if domain == "schedule":
        if operation in {"QUERY", "LIST", "SEARCH", "CALENDAR"}:
            return domain, "schedule.query", "metadata_query"
        if operation in {"CREATE", "CREATE_DRAFT", "NEW"}:
            return domain, "schedule.create", "workflow"
        if operation in {"UPDATE", "EDIT"}:
            return domain, "schedule.update", "workflow"
        if operation in {"CANCEL", "DELETE"}:
            return domain, "schedule.cancel", "workflow"
    if domain == "party_file":
        if operation in {"ATTACHMENTS", "ATTACHMENT", "ATTACHMENT_QUERY"}:
            return domain, "party_file.attachments", "metadata_query"
        if operation in {"CREATE", "PUBLISH", "DRAFT", "DRAFT_AND_PUBLISH"}:
            return domain, "party_file.create", "workflow"
        if operation in {"UPDATE", "EDIT"}:
            return domain, "party_file.update", "workflow"
        if operation in {"DELETE", "REMOVE", "VOID"}:
            return domain, "party_file.delete", "workflow"
        if operation in {"QUERY", "LIST", "SEARCH", "METADATA_QUERY"}:
            return domain, "party_file.metadata", "metadata_query"
    return None


def _recover_typed_workflow_candidate(
    message: str,
    candidate_plan: dict[str, Any] | None,
    query_intent: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Normalize a provider's partially emitted typed workflow envelope.

    Some OpenAI-compatible providers emit ``query_intent`` but omit the
    top-level ``capability_id`` and ``candidate_plan`` fields.  The query
    intent is still a structured object, so losing those fields should not
    send an otherwise unambiguous request into the ReAct fallback.  This
    helper only accepts explicit domain/shape markers; it never classifies
    free-form prose.
    """
    candidate = dict(candidate_plan) if isinstance(candidate_plan, dict) else {}
    intent = dict(query_intent) if isinstance(query_intent, dict) else {}

    # Some providers emit a typed personal-schedule payload but omit the
    # entity/domain field. Recover that omission only when the user message
    # explicitly names a personal schedule and the payload contains the
    # structured fields that prove it. A generic CREATE remains ambiguous.
    text = str(message or "")
    explicit_personal_schedule = bool(re.search(r"个人日程|个人安排|我的日程", text))
    merged = {**intent, **candidate}
    nested_fields = candidate.get("draft_fields") or candidate.get("draftFields")
    if isinstance(nested_fields, dict):
        merged = {**nested_fields, **merged}

    # Some providers put the complete party-file intent in query_intent but
    # omit candidate_plan. This is typed schema recovery, not prose routing.
    # Keep confirmation distinct from CREATE: only an official ApprovalCard
    # resume may call confirm_* and a plain “确认发布” must not mint a draft.
    party_action = str(intent.get("action") or intent.get("operation") or "").strip().upper().replace("-", "_")
    party_domain = str(
        intent.get("entity") or intent.get("domain") or intent.get("type") or intent.get("document_type") or ""
    ).strip().lower().replace("-", "_")
    party_shape = any(
        intent.get(key) not in (None, "", [], {})
        for key in ("title", "document_type", "date_range", "audience", "activities", "requirement", "background", "confirmation")
    )
    party_action_is_typed = any(marker in party_action for marker in (
        "PARTY_FILE", "PARTY_DOCUMENT", "DRAFT_AND_PUBLISH", "PUBLISH_PARTY", "CREATE_PARTY",
    ))
    # Providers may emit a generic CRUD operation together with a typed
    # ``document_type``/``title`` intent, while omitting both the party-file
    # entity and the longer ``draft_and_publish_party_document`` action.  That
    # envelope is still unambiguous: a document type plus a title is not a
    # meeting or personal-schedule plan.  Recover the registered party-file
    # workflow instead of delegating to the read-only child agent.
    typed_party_document = bool(
        str(intent.get("document_type") or intent.get("documentType") or "").strip()
        and str(intent.get("title") or "").strip()
    )
    if party_action_is_typed or party_domain in {"party_file", "party_files", "party_document", "party_notice"} or typed_party_document:
        confirmation_action = "CONFIRM" in party_action or bool(intent.get("confirmation"))
        if confirmation_action:
            return {**candidate, **intent, "entity": "party_file", "operation": "CONFIRM", "_confirmation_intent": True}
        party_operation = normalize_party_file_operation(
            intent.get("operation") or intent.get("action")
        )
        party_operation = {
            "DRAFT_AND_PUBLISH_PARTY_DOCUMENT": "CREATE",
            "PUBLISH_PARTY_FILE": "CREATE",
        }.get(party_operation, party_operation)
        if party_operation in {"CREATE", "UPDATE", "DELETE"} or party_shape:
            return {**candidate, **intent, "entity": "party_file", "operation": party_operation or "CREATE"}
    operation = str(merged.get("operation") or merged.get("action") or "").strip().upper()
    operation = {
        "NEW": "CREATE", "CREATE_DRAFT": "CREATE", "CREATE_SCHEDULE": "CREATE",
        "CREATE_PERSONAL_SCHEDULE": "CREATE", "UPDATE_SCHEDULE": "UPDATE",
        "EDIT": "UPDATE", "CHANGE": "UPDATE", "RESCHEDULE": "UPDATE",
        "CANCEL": "CANCEL", "DELETE": "CANCEL", "DELETE_SCHEDULE": "CANCEL",
    }.get(operation, operation)
    has_schedule_fields = (
        bool(str(merged.get("title") or merged.get("summary") or "").strip())
        and any(merged.get(key) not in (None, "") for key in ("start_time", "startTime", "start"))
        and any(merged.get(key) not in (None, "") for key in ("end_time", "endTime", "end"))
    )
    typed_schedule = explicit_personal_schedule and operation in {"CREATE", "UPDATE", "CANCEL"} and (
        has_schedule_fields or any(
            key in merged for key in ("source_schedule_id", "sourceScheduleId", "schedule_id", "scheduleId")
        )
    )
    if typed_schedule:
        normalized = {**candidate, **intent, "type": "personal_schedule", "operation": operation}
        if isinstance(nested_fields, dict):
            normalized = {**nested_fields, **normalized}
        normalized["entity"] = "personal_schedule"
        return normalized

    if candidate:
        return candidate
    if not intent:
        return None

    raw_domain = intent.get("entity") or intent.get("domain") or intent.get("type")
    domain = str(raw_domain or "").strip().lower().replace("-", "_")
    meeting_markers = {
        "meeting", "meeting_room", "meeting_booking", "meetingroom",
        "room_booking", "conference_room", "会议", "会议室",
    }
    schedule_markers = {
        "schedule", "personal_schedule", "calendar", "日程", "个人日程",
    }

    # ``attendees`` plus a bounded start/end interval is the typed shape used
    # by the meeting-booking planner.  It is intentionally not a prose or
    # keyword route; callers that do not provide this shape remain fallback.
    is_meeting = domain in meeting_markers or (
        "attendees" in intent
        and any(key in intent for key in ("start_time", "start"))
        and any(key in intent for key in ("end_time", "end"))
    )
    is_schedule = domain in schedule_markers
    if not is_meeting and not is_schedule:
        return None

    operation = str(
        intent.get("operation")
        or intent.get("action")
        or ""
    ).strip().upper()
    operation = {
        "CREATE": "BOOK" if is_meeting else "CREATE",
        "NEW": "BOOK" if is_meeting else "CREATE",
        "BOOK": "BOOK",
        "UPDATE": "UPDATE",
        "EDIT": "UPDATE",
        "CHANGE": "UPDATE",
        "RESCHEDULE": "UPDATE",
        "CANCEL": "CANCEL",
        "DELETE": "CANCEL",
        "REMOVE": "CANCEL",
    }.get(operation, operation)
    if operation not in {"BOOK", "UPDATE", "CANCEL", "CREATE"}:
        return None
    if is_meeting and operation == "CREATE":
        operation = "BOOK"
    # Preserve the structured business fields when only the outer route
    # envelope was dropped.  Returning only operation/type silently discarded
    # start/end/title and made strict action validation ask for fields the
    # provider had already extracted.
    return {
        **intent,
        "operation": operation,
        "type": "meeting_booking" if is_meeting else "personal_schedule",
    }


def _is_plain_confirmation_message(message: str) -> bool:
    """Recognize a confirmation utterance without matching confirmation UI text.

    ``确认卡`` and ``待确认草稿`` are descriptions of a pending write, not a
    user's decision to submit it.  Treating the substring ``确认`` as a
    confirmation signal made normal draft requests skip action selection and
    lose their executor.  Only a small, punctuation-tolerant set of complete
    confirmation utterances is allowed to enter the safe resume clarification.
    """
    text = re.sub(r"[\s，,。！？!?；;：:、]+", "", str(message or "").strip())
    if not text or re.search(r"确认(?:卡|草稿|信息|按钮|字段)", text):
        return False
    if text in {"确认", "同意", "批准", "确认发布", "确认提交", "确认通过", "同意发布", "同意提交"}:
        return True
    return bool(re.fullmatch(r"(?:我|用户)?(?:已|现在)?确认(?:发布|提交|通过)", text))


def _recover_typed_schedule_query_candidate(
    message: str,
    candidate_plan: dict[str, Any] | None,
    query_intent: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Recover a schedule metadata query when the provider drops its envelope.

    The recovery is limited to a typed personal-schedule query shape. It does
    not inspect arbitrary prose for a route; the explicit operation plus a
    date/range field must already be present in the candidate/query object.
    """
    candidate = dict(candidate_plan) if isinstance(candidate_plan, dict) else {}
    intent = dict(query_intent) if isinstance(query_intent, dict) else {}
    merged = {**intent, **candidate}
    operation = str(merged.get("operation") or merged.get("action") or "").strip().upper()
    operation = {"LIST": "QUERY", "SEARCH": "QUERY", "CALENDAR": "QUERY"}.get(operation, operation)
    schedule_type = str(
        merged.get("schedule_type") or merged.get("scheduleType")
        or merged.get("entity") or merged.get("type") or ""
    ).strip().lower().replace("-", "_")
    date = str(merged.get("date") or "").strip()
    start = str(merged.get("start_time") or merged.get("startTime") or "").strip()
    end = str(merged.get("end_time") or merged.get("endTime") or "").strip()
    # ``schedule_type=personal`` is already a typed domain assertion from the
    # planner. The message check is only a secondary guard for providers that
    # omit that field; do not require the model to repeat the word ``个人`` in
    # a shortened route message.
    explicit_schedule = schedule_type in {"personal", "personal_schedule", "schedule", "calendar"} or bool(
        re.search(r"个人日程|个人安排|我的日程|个人日历|我的日历", str(message or ""))
    )
    if operation != "QUERY" or not explicit_schedule or schedule_type not in {"personal", "personal_schedule", "schedule", "calendar"}:
        return None
    if not date and not (start and end):
        return None
    return {**candidate, **intent, "entity": "personal_schedule", "operation": "QUERY"}


@tool(args_schema=RouteConversationInput)
def route_conversation(
    message: str,
    task_complexity: Literal["simple", "complex"] = "simple",
    capability_id: str | None = None,
    action_id: str | None = None,
    strategy: RouteStrategy | None = None,
    confidence: float | None = None,
    missing_fields: list[str] | None = None,
    unsupported_criteria: list[str] | None = None,
    query_intent: dict | str | None = None,
    execution_class: ExecutionClass | None = None,
    candidate_plan: dict[str, Any] | str | None = None,
) -> ToolResponse:
    """校验主 Agent 提出的能力选择和任务复杂度，不执行业务操作。

    capability_id 必须来自当前能力目录；不确定时传 general_agent，不能
    编造未注册的业务能力。已选择领域后，action_id 必须来自该领域的动作目录；
    模型不能传工具名或 Java 路径。Runtime 会校验 direct/delegate/clarify 边界。
    """
    # Keep the public schema tolerant of the provider's object-as-string
    # encoding, then immediately restore the canonical in-memory shape.  No
    # business routing is inferred from the user's prose here.
    candidate_plan = _coerce_object(candidate_plan)
    explicit_candidate_supplied = isinstance(candidate_plan, dict) and bool(candidate_plan)
    query_intent = _coerce_object(query_intent)
    action_id = str(
        action_id
        or (candidate_plan or {}).get("action_id")
        or (candidate_plan or {}).get("actionId")
        or (query_intent or {}).get("action_id")
        or (query_intent or {}).get("actionId")
        or ""
    ).strip() or None
    # Conversation history is carried by the LangGraph checkpoint. It is not
    # a mutable business fact source, so route recovery never selects a write
    # target from a thread-wide Redis task projection. UPDATE/CANCEL plans must
    # carry an explicit, compiler-authorized source ID.
    route = classify_message(message, task_complexity=task_complexity)
    party_file_attachment = party_file_attachment_plan(message, candidate_plan, capability_id)
    # Structured source IDs are accepted only from the candidate plan and are
    # revalidated by the domain compiler/Java facade. A free-form follow-up
    # without an explicit source must remain a clarification.
    # Attachment inspection/delivery has precedence over party-file CRUD. A
    # provider-produced CREATE candidate cannot override this read-only
    # boundary when the user did not ask to create or publish a document.
    if party_file_attachment and party_file_attachment.get("status") == "RESOLVED":
        capability_id = "party_file"
        action_id = "party_file.attachments"
        execution_class = "metadata_query"
        candidate_plan = {
            "operation": "ATTACHMENTS",
            "source_party_file_id": party_file_attachment["source_party_file_id"],
            "action": "inspect",
            "_authorized_source_fields": party_file_attachment.get("_authorized_source_fields", []),
        }
        strategy = "direct"
        confidence = 1.0
        explicit_candidate_supplied = True
    elif party_file_attachment and party_file_attachment.get("status") == "CLARIFY":
        capability_id = "party_file"
        execution_class = "metadata_query"
        strategy = "clarify"
        confidence = 1.0
        candidate_plan = {"operation": "ATTACHMENTS"}
        # Do not retain a provider's CREATE payload while asking for the
        # source file. Otherwise a clarification turn could mint a draft.
        explicit_candidate_supplied = False
    # OpenAI-compatible providers occasionally omit one of the routing
    # envelope fields while still returning a typed, registered operation
    # (for example ``candidate_plan={operation: BOOK}``).  Recover only this
    # schema-level fact; never infer from free-form user prose.  A known
    # operation is sufficient to recover both the workflow class and domain,
    # otherwise the request remains on the general fallback path.
    recovered_candidate = _recover_typed_workflow_candidate(message, candidate_plan, query_intent)
    if recovered_candidate is not None:
        candidate_plan = recovered_candidate
    recovered_schedule_query = _recover_typed_schedule_query_candidate(message, candidate_plan, query_intent)
    if recovered_schedule_query is not None:
        candidate_plan = recovered_schedule_query
        if not capability_id or str(capability_id).strip() in {"general_agent", "general"}:
            capability_id = "schedule"
        if execution_class in {None, "metadata_query"}:
            execution_class = "metadata_query"
    recovered_party_file = recover_party_file_write_candidate(message, candidate_plan)
    if recovered_party_file is not None:
        candidate_plan = recovered_party_file
        # A typed party-file write is a hard execution-boundary assertion.
        # Never preserve a provider's broad content/document class here: that
        # would compile to FALLBACK and expose the read-only child agent.
        execution_class = "workflow"
        capability_id = "party_file"
    # A provider can drop the complete typed candidate, not just one envelope
    # field.  Do one bounded recovery for an unmistakable party-file write so
    # a supported request cannot fall through to general-agent prose.  This
    # helper intentionally returns only the operation/entity; business fields
    # and all authorization facts still come from the normal draft tool and
    # Java facade.
    if recovered_party_file is None:
        recovered_party_file_intent = recover_party_file_write_intent(message, candidate_plan)
        if recovered_party_file_intent is not None:
            candidate_plan = recovered_party_file_intent
            execution_class = "workflow"
            capability_id = "party_file"

    # A confirmation is a resume signal for a persisted ApprovalCard, not a
    # new business action.  Keep it out of the ordinary action-selection
    # handshake: that handshake is for choosing CREATE/UPDATE/DELETE, while a
    # plain confirmation must never mint a new draft or expose a write tool.
    # The marker is produced only by the typed party-file confirmation shape;
    # the message-only branch below is limited to an already selected
    # party-file capability so a generic "确认" cannot be misrouted.
    confirmation_intent = bool(
        isinstance(candidate_plan, dict)
        and (
            candidate_plan.get("_confirmation_intent") is True
            or str(candidate_plan.get("operation") or candidate_plan.get("action") or "")
            .strip()
            .upper()
            in {"CONFIRM", "CONFIRM_PUBLISH", "CONFIRM_RELEASE"}
        )
    )
    if not confirmation_intent and str(capability_id or "").strip().lower() in {
        "party_file", "party_files", "party_files_agent"
    } and _is_plain_confirmation_message(message):
        confirmation_intent = True
        capability_id = "party_file"
        execution_class = "workflow"
        candidate_plan = {
            "entity": "party_file",
            "operation": "CONFIRM",
            "_confirmation_intent": True,
        }
    if confirmation_intent:
        # A stale provider action id (for example party_file.create) must not
        # survive a confirmation-only turn. The durable ApprovalCard owns the
        # operation; this route call only explains how to resume it.
        action_id = None
        candidate_plan = {
            "entity": "party_file",
            "operation": "CONFIRM",
            "_confirmation_intent": True,
        }

    # A provider can select the approval-read domain while dropping the
    # second-stage action and typed query envelope. Repeating the same route
    # call cannot add information and was observed to create a loop. Recover
    # only the domain-scoped, structurally unambiguous list/analysis action;
    # all other approval requests still receive ACTION_SELECTION.
    if (
        not confirmation_intent
        and not action_id
        and str(capability_id or "").strip().lower() in {
            "approval_read", "approval", "approvals", APPROVAL_PROCESS_CAPABILITY_ID,
        }
        and not candidate_plan
        and not query_intent
        and not unsupported_criteria
        and not missing_fields
    ):
        recovered_process = recover_approval_process_action(message)
        if recovered_process is not None:
            # The explicit owner or history scope belongs to
            # approval_process, whether the model selected the inbox domain
            # or the process domain but omitted the second-stage action.
            # Correct only this registered overlap; do not infer arbitrary
            # approval actions.
            capability_id = "approval_process"
            action_id = recovered_process["action_id"]
            execution_class = recovered_process.get("execution_class") or execution_class
            candidate_plan = dict(recovered_process.get("candidate_plan") or {})
            explicit_candidate_supplied = True
        elif str(capability_id or "").strip().lower() in {
            "approval_read", "approval", "approvals",
        }:
            recovered_approval = recover_approval_read_action(message)
            if recovered_approval is not None:
                action_id = recovered_approval["action_id"]
                execution_class = recovered_approval.get("execution_class") or execution_class
                candidate_plan = dict(recovered_approval.get("candidate_plan") or {})
                query_intent = dict(recovered_approval.get("query_intent") or {}) or query_intent
                explicit_candidate_supplied = True

    inferred_workflow = infer_workflow_capability(candidate_plan)
    if inferred_workflow and (not execution_class or execution_class == "workflow"):
        execution_class = "workflow"
    if (not capability_id or str(capability_id).strip() in {"general_agent", "general"}) and execution_class == "workflow":
        capability_id = inferred_workflow
    # Typed read plans produced by the route adapter have an unambiguous
    # action even when a provider omitted the redundant action_id envelope.
    # This is not operation-only model compatibility: these branches are
    # bounded by the already selected domain and execution class.
    if not action_id:
        if capability_id == "approval_read" and query_intent is not None:
            action_id = "approval.read.pending"
        elif capability_id == "schedule" and execution_class == "metadata_query":
            action_id = "schedule.query"
        elif capability_id == "party_file" and execution_class == "metadata_query":
            operation_hint = str((candidate_plan or {}).get("operation") or "").upper()
            action_id = "party_file.attachments" if operation_hint in {"ATTACHMENTS", "ATTACHMENT"} else "party_file.metadata"
    typed_action = _infer_typed_action_from_shape(
        capability_id, execution_class, candidate_plan, query_intent, message
    )
    if typed_action and not action_id:
        typed_capability, typed_action_id, typed_class = typed_action
        capability_id = typed_capability
        action_id = typed_action_id
        execution_class = typed_class
        candidate_plan = {
            **(candidate_plan or {}),
            "action_id": typed_action_id,
            "_action_id_synthesized": True,
        }
        # A typed approval list/rank payload can be normalized into the
        # canonicalizer's vocabulary without asking the model for a second
        # free-form decision.
        if typed_action_id == "approval.read.pending" and query_intent is None:
            raw_sorts = (candidate_plan or {}).get("sort") or []
            normalized_sorts = []
            for item in raw_sorts:
                if not isinstance(item, dict):
                    continue
                field = {"createTime": "created_time", "create_time": "created_time"}.get(
                    str(item.get("field") or ""), str(item.get("field") or "")
                )
                direction = str(item.get("direction") or item.get("order") or "DESC").upper()
                normalized_sorts.append({"field": field, "direction": direction})
            query_intent = {
                "entity": "pending_approval",
                "operation": "rank" if normalized_sorts else "list",
                "sort": normalized_sorts,
                "limit": (candidate_plan or {}).get("limit"),
            }
    proposed_operation = str(
        (candidate_plan or {}).get("operation")
        or (candidate_plan or {}).get("action")
        or (query_intent or {}).get("operation")
        or (query_intent or {}).get("action")
        or ""
    ).strip() or None
    action_id_was_explicit = bool(action_id)
    selected_action = resolve_action(capability_id, action_id, proposed_operation)
    if selected_action is not None:
        action_id = selected_action.action_id
        execution_class = selected_action.execution_class
        candidate_plan = {
            **(candidate_plan or {}),
            "action_id": selected_action.action_id,
            "operation": selected_action.operation,
        }
        if not action_id_was_explicit:
            candidate_plan["_action_id_synthesized"] = True
        explicit_candidate_supplied = True
    elif action_id:
        # Keep the invalid action visible to the compiler as a structured
        # unsupported action; never silently turn it into a generic fallback.
        candidate_plan = {**(candidate_plan or {}), "action_id": action_id}
        explicit_candidate_supplied = True
    decision = resolve_capability(
        capability_id if capability_routing_enabled() else None,
        strategy if capability_routing_enabled() else None,
        confidence if capability_routing_enabled() else None,
        unsupported_criteria if capability_routing_enabled() else None,
        missing_fields if capability_routing_enabled() else None,
    )
    action_selection_required = (
        decision["capabilityId"] != "general_agent"
        and not confirmation_intent
        and selected_action is None
        and not action_id
        and query_intent is None
        and not unsupported_criteria
        and not missing_fields
        and party_file_attachment is None
    )
    if action_selection_required:
        decision["strategy"] = "clarify"
    # A malformed provider tool call may omit all routing arguments (or leave
    # the generic ``content_search`` class behind).  Recover only the narrow,
    # unambiguous structured metadata case; every other unknown request keeps
    # the general-agent fallback and never gets forced into a business path.
    fallback_plan = party_metadata_fallback_plan(message)
    if fallback_plan is not None and decision["capabilityId"] == "general_agent":
        capability_id = fallback_plan["capability_id"]
        execution_class = fallback_plan["execution_class"]
        candidate_plan = fallback_plan["candidate_plan"]
        decision = resolve_capability(capability_id, "direct", 0.9)
    schedule_fallback_plan = schedule_metadata_fallback_plan(message)
    if schedule_fallback_plan is not None and decision["capabilityId"] == "general_agent":
        capability_id = schedule_fallback_plan["capability_id"]
        execution_class = schedule_fallback_plan["execution_class"]
        candidate_plan = schedule_fallback_plan["candidate_plan"]
        decision = resolve_capability(capability_id, "direct", 0.9)
    query_resolution = None
    if decision["capabilityId"] == "approval_read" and query_intent is not None:
        query_resolution = canonicalize_approval_query(query_intent)
        if query_resolution.status == "CLARIFY":
            decision["strategy"] = "clarify"
    compiled_plan = None
    if not confirmation_intent:
        compiled_plan = compile_plan(
            capability_id=decision["capabilityId"],
            execution_class=execution_class,
            candidate_plan=candidate_plan,
            query_intent=query_intent,
        )
    if compiled_plan is not None:
        if compiled_plan.status == "RESOLVED":
            decision["strategy"] = "direct"
        elif compiled_plan.status in {"CLARIFY", "UNSUPPORTED"}:
            decision["strategy"] = "clarify"
        elif query_resolution is not None and query_resolution.status in {"INVALID", "UNSUPPORTED"}:
            decision["strategy"] = "clarify"
    # The main Agent supplies this two-value performance classification. The
    # router only normalizes it; safety floors in set_route_reasoning_policy
    # can still raise a simple label to low for writes or confirmations.
    route.task_complexity = task_complexity
    route.reasoning_effort = "off" if task_complexity == "simple" else "low"
    route.capability_id = decision["capabilityId"]
    route.strategy = decision["strategy"]
    route.execution_class = compiled_plan.execution_class if compiled_plan is not None else execution_class
    route.confidence = decision["confidence"]
    route.missing_fields = [str(value).strip() for value in (missing_fields or []) if str(value).strip()]
    route.unsupported_criteria = decision["unsupportedCriteria"]
    # The main Agent calls this Tool before it delegates. Store the validated
    # policy once so every later main/sub-agent model call in this Run shares
    # it without a second LLM classification request.
    set_route_reasoning_policy(route, message)
    result = route.model_dump()
    result["routeDecision"] = decision
    if action_id:
        result["routeDecision"]["actionId"] = action_id
        result["actionId"] = action_id
    if action_selection_required:
        result["routePhase"] = "ACTION_SELECTION"
        result["planStatus"] = "CLARIFY"
        result["actionSelection"] = {
            "required": True,
            "capabilityId": decision["capabilityId"],
            "catalog": action_catalog_prompt(decision["capabilityId"]),
            # Preserve typed values extracted during a provider retry.  The
            # next routing call must add only ``action_id`` and may reuse this
            # payload; dropping it was causing repeated route calls and made
            # the model fall back to the generic task tool.
            "candidatePlan": candidate_plan or {},
            "queryIntent": query_intent or {},
            "nextRequiredFields": ["action_id"],
            "actions": [
                {
                    "actionId": item.action_id,
                    "label": action_description(item),
                    "executionClass": action_execution_class(item),
                    "readOnly": action_read_only(item),
                    "requiresConfirmation": action_requires_confirmation(item),
                    "requiredFields": list(action_required_fields(item)),
                    "fields": [
                        {
                            "name": field.name,
                            "type": field.field_type,
                            "required": field.required,
                            "nullable": field.nullable,
                            "description": field.description,
                            "sourcePolicy": field.source_policy,
                        }
                        for field in action_field_specs(item)
                    ],
                }
                for item in actions_for_capability(decision["capabilityId"])
            ],
        }
        result["clarification"] = {
            "status": "ACTION_SELECTION",
            "question": "请从当前领域动作目录中选择一个具体业务动作。",
            "issues": [],
            "missingFields": ["action_id"],
            "nextRequiredFields": ["action_id"],
            "suggestedActionId": _suggest_action_id_from_payload(
                decision["capabilityId"], candidate_plan, query_intent
            ),
            "options": result["actionSelection"]["actions"],
        }
    if confirmation_intent:
        # Do not expose an executor or a synthetic action id.  A valid
        # ApprovalCard resume is handled by the graph's interrupt/resume
        # boundary; a free-form confirmation only receives this safe
        # clarification when no such card is present in the current run.
        result["planStatus"] = "CLARIFY"
        result["clarification"] = {
            "status": "CLARIFY",
            "question": "请点击当前党务文件确认卡完成发布，不能通过普通文本直接提交。",
            "issues": ["普通文本确认不能替代党务文件 ApprovalCard"],
            "missingFields": [],
        }
    if decision["capabilityId"] == APPROVAL_PROCESS_CAPABILITY_ID and not (
        compiled_plan is not None and compiled_plan.status == "RESOLVED"
    ):
        # The capability is registered, but the model did not provide a
        # complete operation plan.  This is a planning clarification, not a
        # facade outage: the user must choose applications, one application,
        # history, or withdrawal and provide the fields required by that
        # operation.  Never claim that a supported operation is unavailable.
        result["clarification"] = {
            "status": "CLARIFY",
            "question": "请说明要查看我发起的审批、某条审批详情、已办审批历史，还是撤回本人仍在运行中的流程；撤回还需要流程实例编号和理由。",
            "issues": ["审批流程操作计划不完整"],
            "missingFields": [],
            "options": [
                {"operation": "APPLICATIONS", "label": "我发起的审批"},
                {"operation": "APPLICATION_DETAIL", "label": "某条审批详情", "requiredFields": ["processInstanceId"]},
                {"operation": "HISTORY", "label": "已办审批历史"},
                {"operation": "WITHDRAW", "label": "撤回本人审批", "requiredFields": ["processInstanceId", "reason"]},
            ],
        }
    if compiled_plan is not None:
        result["plan"] = compiled_plan.model_dump(mode="json")
        result["planStatus"] = compiled_plan.status
        if compiled_plan.execution_tool:
            result["routeDecision"]["executionTool"] = compiled_plan.execution_tool
            result["executionTool"] = compiled_plan.execution_tool
            result["executionPlan"] = compiled_plan.canonical
            result["planId"] = compiled_plan.plan_id
        # The action-catalog clarification is the higher-level contract when
        # an approval-process route has no action_id at all.  Do not let the
        # domain compiler's lower-level wording overwrite that stable choice;
        # otherwise the UI reports a different question than the action
        # selection payload exposes.
        if compiled_plan.status in {"CLARIFY", "UNSUPPORTED"} and not (
            decision["capabilityId"] == APPROVAL_PROCESS_CAPABILITY_ID
            and action_selection_required
        ):
            result["clarification"] = {
                "status": compiled_plan.status,
                "question": compiled_plan.clarification_question or "请补充或确认这项任务的查询条件。",
                "issues": compiled_plan.issues,
                "missingFields": compiled_plan.missing_fields,
            }
    if query_resolution is not None:
        result["queryResolution"] = query_resolution.model_dump(mode="json", by_alias=True)
        if query_resolution.status == "RESOLVED" and query_resolution.plan is not None:
            # The rule layer owns execution semantics. Once resolved, the
            # model must not choose among overlapping list/search/analyze
            # tools or change the operation order on a retry.
            execution_plan = query_resolution.plan.model_dump(mode="json")
            result["routeDecision"]["executionTool"] = "run_approval_query_plan"
            result["routeDecision"]["executionPlan"] = execution_plan
            result["executionTool"] = "run_approval_query_plan"
            result["executionPlan"] = execution_plan
        elif query_resolution.status in {"CLARIFY", "INVALID", "UNSUPPORTED"}:
            result["clarification"] = {
                "status": query_resolution.status,
                "question": query_resolution.clarification_question or "请补充或确认审批查询条件。",
                "issues": query_resolution.issues,
                "options": query_resolution.alternatives,
            }
    if party_file_attachment and party_file_attachment.get("status") == "CLARIFY":
        result["clarification"] = {
            "status": "CLARIFY",
            "question": party_file_attachment["message"],
            "issues": ["source_party_file_id"],
            "missingFields": ["source_party_file_id"],
            "options": party_file_attachment.get("options", []),
        }
    try:
        writer = get_stream_writer()
    except RuntimeError:
        writer = None
    if writer is not None:
        emit(
            writer,
            "route.selected",
            f"已选择能力 {decision['capabilityId']}，执行策略为 {decision['strategy']}",
            capabilityId=decision["capabilityId"],
            actionId=action_id,
            strategy=decision["strategy"],
            confidence=decision["confidence"],
            missingFields=decision["missingFields"],
            unsupportedCriteria=decision["unsupportedCriteria"],
        )
        if compiled_plan is not None:
            emit(
                writer,
                "plan.compiled",
                f"已编译任务计划：{compiled_plan.status}",
                planId=compiled_plan.plan_id,
                planStatus=compiled_plan.status,
                capabilityId=compiled_plan.capability_id,
                executionClass=compiled_plan.execution_class,
                executionTool=compiled_plan.execution_tool,
                issues=compiled_plan.issues,
            )
    presentation = None
    if action_selection_required:
        presentation = {
            "blockType": "card",
            "cardType": "clarification",
            "resultKind": "clarification",
            "summary": {"headline": "请先选择具体业务动作"},
            "actions": result["actionSelection"]["actions"],
        }
    elif confirmation_intent:
        presentation = {
            "blockType": "card",
            "cardType": "clarification",
            "resultKind": "clarification",
            "summary": {"headline": "请使用党务文件确认卡完成发布"},
            "actions": [],
        }
    elif decision["capabilityId"] == APPROVAL_PROCESS_CAPABILITY_ID and not (
        compiled_plan is not None and compiled_plan.status == "RESOLVED"
    ):
        presentation = {
            "blockType": "card",
            "cardType": "clarification",
            "resultKind": "clarification",
            "summary": {"headline": "请先选择审批流程操作"},
            "actions": [
                {"operation": "APPLICATIONS", "label": "我发起的审批"},
                {"operation": "APPLICATION_DETAIL", "label": "某条审批详情"},
                {"operation": "HISTORY", "label": "已办审批历史"},
                {"operation": "WITHDRAW", "label": "撤回本人审批"},
            ],
        }
    elif query_resolution is not None and query_resolution.status in {"CLARIFY", "INVALID", "UNSUPPORTED"}:
        presentation = {
            "blockType": "card",
            "cardType": "clarification",
            "resultKind": "clarification",
            "summary": {"headline": "需要确认审批查询口径"},
            "actions": query_resolution.alternatives,
        }
    elif party_file_attachment and party_file_attachment.get("status") == "CLARIFY":
        presentation = {
            "blockType": "card",
            "cardType": "clarification",
            "resultKind": "clarification",
            "summary": {"headline": "请先选择要核对附件的党务文件"},
            "actions": party_file_attachment.get("options", []),
        }
    return tool_success(result, presentation)
