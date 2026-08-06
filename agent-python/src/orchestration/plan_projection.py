"""Project only the executor selected by the compiled TaskPlan."""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware

from .phase_prompt import classify_main_agent_phase
from .route_state import (
    current_turn_messages as _current_turn_messages,
    is_terminal_structured_failure as _is_terminal_structured_failure,
    message_content as _content,
    message_name as _tool_name,
    message_type as _message_type,
    route_requires_action_selection as _route_requires_action_selection,
    route_result as _route_result,
)


class PlanToolProjectionMiddleware(AgentMiddleware):
    """Mask unrelated tools after a plan has been compiled.

    Before ``route_conversation`` returns, the normal DeepAgents tool palette
    is preserved. Once it returns a RESOLVED plan, only that plan's executor
    remains visible. This keeps the existing DeepAgents loop and checkpoint
    semantics while removing accidental cross-domain tool selection.
    """

    name = "PlanToolProjectionMiddleware"

    @staticmethod
    def _override(request):
        import logging
        _log = logging.getLogger(__name__)
        state = getattr(request, "state", {}) or {}
        messages = list(state.get("messages") or [])
        turn_messages = _current_turn_messages(messages)
        route = _route_result(turn_messages)
        _log.warning(
            "plan projection: messages=%s turn=%s route=%s latest_tool=%s phase=%s tools=%s",
            len(messages), len(turn_messages),
            {k: route.get(k) for k in ("planStatus", "executionTool", "execution_class")} if route else None,
            next((_tool_name(message) for message in reversed(messages) if _message_type(message) == "tool"), ""),
            classify_main_agent_phase(messages),
            [getattr(item, "name", None) or (item.get("name") if isinstance(item, dict) else None) for item in request.tools],
        )
        if not route:
            # The parent must classify a business turn before it can call a
            # domain tool or delegate.  Prompt instructions alone are not a
            # reliable barrier: providers can emit ``task`` directly.  Keep
            # only the planning primitives visible until route_conversation
            # has returned for this turn.  Simple chat still has no tool call,
            # so it remains unaffected.
            planning_names = {"report_progress", "route_conversation"}
            allowed = []
            for item in request.tools:
                name = getattr(item, "name", None)
                if isinstance(item, dict):
                    name = name or item.get("name")
                if name in planning_names:
                    allowed.append(item)
            return request.override(tools=allowed)
        executor = route.get("executionTool")
        latest_tool = next((_tool_name(message) for message in reversed(messages) if _message_type(message) == "tool"), "")
        if classify_main_agent_phase(messages) == "synthesizing" or (executor and latest_tool == executor):
            # The synthesis phase must not start a new business operation.
            # A confirmed interrupt resumes its already-persisted ToolCall
            # through LangGraph's ToolNode; it never needs to be made visible
            # to a later model call. Re-exposing a pending confirmation tool
            # here would let ordinary text recreate a durable write path.
            return request.override(tools=[])
        if _route_requires_action_selection(route):
            # The first routing stage has selected only a domain.  Expose no
            # business executor or delegation tool until the model submits a
            # registered action_id in the second routing stage.
            planning_names = {"report_progress", "route_conversation"}
            allowed = []
            for item in request.tools:
                name = getattr(item, "name", None)
                if isinstance(item, dict):
                    name = name or item.get("name")
                if name in planning_names:
                    allowed.append(item)
            return request.override(tools=allowed)
        if not executor or route.get("planStatus") != "RESOLVED":
            # A malformed or unsupported route must never reopen the entire
            # business-tool palette.  Keep only the generic delegation and
            # memory tools so the domain ReAct fallback can handle it without
            # accidentally invoking a structured executor with ``{}``.
            # For write workflows in the registered deterministic domains,
            # ``task`` is also unsafe: delegation would bypass the missing
            # operation/field clarification and land in a read-only child
            # agent.  The user must complete the structured plan first.
            is_write_workflow_clarify = (
                route.get("planStatus") in {"CLARIFY", "UNSUPPORTED"}
                and route.get("execution_class") == "workflow"
                and route.get("capabilityId") in {"party_file", "meeting", "schedule"}
            )
            allowed_names = (
                {"report_progress"}
                if is_write_workflow_clarify or _is_terminal_structured_failure(route)
                else {"task", "report_progress"}
            )
            allowed = []
            for item in request.tools:
                name = getattr(item, "name", None)
                if isinstance(item, dict):
                    name = name or item.get("name")
                if name in allowed_names:
                    allowed.append(item)
            return request.override(tools=allowed)
        allowed = []
        for item in request.tools:
            name = getattr(item, "name", None)
            if isinstance(item, dict):
                name = name or item.get("name")
            if name == executor:
                allowed.append(item)
        return request.override(tools=allowed) if allowed else request

    def wrap_model_call(self, request, handler):
        return handler(self._override(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._override(request))

    @staticmethod
    def _inject_compiled_plan(request):
        """Bind the canonical plan to the projected executor call.

        Some providers emit a tool call with an empty/partial argument object
        even though the route tool already returned the canonical execution
        plan.  Letting that call reach the executor makes the executor reject
        it and causes the ReAct loop to retry indefinitely.  The route result
        is the authoritative source, so the middleware fills (and replaces)
        the public ``plan`` argument at the tool boundary.  This keeps the
        model free to choose *whether* to execute while code owns *what* is
        executed.
        """
        call = dict(getattr(request, "tool_call", None) or {})
        name = str(call.get("name") or "")
        if name == "route_conversation":
            args = dict(call.get("args") or {})
            if not str(args.get("message") or "").strip():
                messages = list((getattr(request, "state", {}) or {}).get("messages") or [])
                for message in reversed(messages):
                    if _message_type(message) not in {"human", "user"}:
                        continue
                    content = _content(message)
                    if isinstance(content, str) and content.strip():
                        args["message"] = content
                        call["args"] = args
                        return request.override(tool_call=call)
            return request
        if name not in {"execute_party_file_metadata_plan", "run_approval_query_plan", "get_my_calendar", "list_my_meeting_bookings", "run_meeting_booking_workflow", "run_personal_schedule_workflow", "create_party_file_draft", "update_party_file_draft", "delete_party_file_draft", "create_approval_withdraw_draft", "approval_report", "meeting_report", "schedule_report", "party_file_report"}:
            return request
        messages = list((getattr(request, "state", {}) or {}).get("messages") or [])
        route = _route_result(_current_turn_messages(messages))
        if not route or route.get("planStatus") != "RESOLVED":
            return request
        executor = route.get("executionTool") or ((route.get("routeDecision") or {}).get("executionTool"))
        canonical = route.get("executionPlan")
        if executor != name or not isinstance(canonical, dict):
            return request
        if name in {"create_party_file_draft", "update_party_file_draft", "delete_party_file_draft"}:
            args = dict(call.get("args") or {})
            # CREATE uses the generic draft schema; UPDATE/DELETE have
            # operation-specific schemas. The compiler owns the operation so
            # a retry cannot switch an update/delete into a publish.
            if name == "create_party_file_draft":
                args["operation"] = "CREATE"
            else:
                source_id = canonical.get("sourcePartyFileId")
                if source_id is not None:
                    args["source_party_file_id"] = source_id
            # The compiler has already validated these values. Re-apply them
            # on every retry so a provider cannot drop category/content or
            # accidentally turn an UPDATE/DELETE into an empty request.
            for key in ("title", "content", "category_name", "summary", "publish_time",
                        "targets", "distribute_to_self", "storage_type", "status"):
                if key in canonical:
                    args[key] = canonical[key]
            if "attachment_file_ids" in canonical:
                attachment_ids = canonical["attachment_file_ids"]
                args["attachment_file_ids"] = (
                    ",".join(str(item) for item in attachment_ids)
                    if isinstance(attachment_ids, list) else attachment_ids
                )
            call["args"] = args
            return request.override(tool_call=call)
        if name == "run_meeting_booking_workflow":
            # Operation and source booking are compiler-owned. Preserve other
            # fields extracted by the model (new time, subject, attendees),
            # but never let a partial retry turn UPDATE into CREATE.
            args = dict(call.get("args") or {})
            operation = canonical.get("operation")
            if operation:
                args["operation"] = operation
            if canonical.get("sourceBookingId") is not None:
                args["source_booking_id"] = canonical["sourceBookingId"]
            field_map = {
                "subject": "subject", "start_time": "start_time", "end_time": "end_time",
                "attendees": "attendee_names", "room_capacity": "room_capacity",
                "equipment": "equipment", "room_preference": "room_preference",
                "remark": "remark", "reason": "cancel_reason",
            }
            for source, target in field_map.items():
                if source in canonical:
                    args[target] = canonical[source]
            call["args"] = args
            return request.override(tool_call=call)
        if name == "run_personal_schedule_workflow":
            # The route boundary owns UPDATE/CANCEL operation and, after a
            # calendar query, the only authorized source schedule ID. A model
            # retry must not lose that binding or switch back to CREATE.
            args = dict(call.get("args") or {})
            operation = canonical.get("operation")
            if operation:
                args["operation"] = operation
            if canonical.get("sourceScheduleId") is not None:
                args["source_schedule_id"] = canonical["sourceScheduleId"]
            field_map = {
                "title": "title", "start_time": "start_time", "end_time": "end_time",
                "description": "description", "location": "location",
                "attendees": "attendee_user_ids", "other_participants": "other_participants",
            }
            for source, target in field_map.items():
                if source in canonical:
                    args[target] = canonical[source]
            call["args"] = args
            return request.override(tool_call=call)
        if name == "get_my_calendar":
            args = dict(call.get("args") or {})
            if canonical.get("startTime") is not None:
                args["start_time"] = canonical["startTime"]
            if canonical.get("endTime") is not None:
                args["end_time"] = canonical["endTime"]
            call["args"] = args
            return request.override(tool_call=call)
        if name == "list_my_meeting_bookings":
            args = dict(call.get("args") or {})
            if canonical.get("startTime") is not None:
                args["start_time"] = canonical["startTime"]
            if canonical.get("endTime") is not None:
                args["end_time"] = canonical["endTime"]
            call["args"] = args
            return request.override(tool_call=call)
        if name == "create_approval_withdraw_draft":
            args = dict(call.get("args") or {})
            if canonical.get("processInstanceId") is not None:
                args["process_instance_id"] = canonical["processInstanceId"]
            if canonical.get("reason") is not None:
                args["reason"] = canonical["reason"]
            call["args"] = args
            return request.override(tool_call=call)
        if name in {"approval_report", "meeting_report", "schedule_report", "party_file_report"}:
            # Reports accept ordinary named arguments, not the generic
            # ``plan`` envelope used by deterministic query executors.
            args = dict(call.get("args") or {})
            for key, value in canonical.items():
                if key not in {"operation", "rangeRequired"}:
                    args[key] = value
            call["args"] = args
            return request.override(tool_call=call)
        call["args"] = {"plan": canonical}
        return request.override(tool_call=call)

    def wrap_tool_call(self, request, handler):
        return handler(self._inject_compiled_plan(request))

    async def awrap_tool_call(self, request, handler):
        return await handler(self._inject_compiled_plan(request))


__all__ = ["PlanToolProjectionMiddleware"]
