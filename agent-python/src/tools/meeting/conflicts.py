from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import os
from typing import Annotated, Any

from langchain.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from ..common import (
    ToolResponse,
    bind_tool_call_id,
    current_agent_context,
    emit,
    java_post,
    java_post_list,
    normalize_local_datetime,
    tool_failure,
    tool_success,
)
from .state import AvailabilityCheckError, save_availability_check
from .support import facade_tool_failure as _facade_tool_failure
from ...runtime.operation_payload import merge_operation_payload, operation_payload
from ...services.meeting_gate import meeting_request_gate


def _extract_attendee_conflicts(calendar_response: Any, *, exclude_booking_id: int | None = None) -> list[dict[str, Any]]:
    """将 Java 日历接口的用户列表转换为统一的冲突列表。

    ``/agent/tools/calendar/users`` 返回的是：
    [{"userId": 1, "userNickname": "...", "events": [...]}]
    旧版 Facade 曾返回过包裹对象，因此这里同时兼容 ``users`` / ``data``
    包装，避免把字典的字符串 key 当成用户对象处理。
    """
    if isinstance(calendar_response, Mapping):
        calendar_response = (
            calendar_response.get("users")
            or calendar_response.get("data")
            or calendar_response.get("items")
            or []
        )
    if not isinstance(calendar_response, list):
        return []

    conflicts: list[dict[str, Any]] = []
    for user in calendar_response:
        if not isinstance(user, Mapping):
            continue
        events = user.get("events") or []
        if not isinstance(events, list):
            continue
        for event in events:
            if (
                exclude_booking_id is not None
                and isinstance(event, Mapping)
                and str(event.get("sourceType") or "") == "MEETING_BOOKING"
                and str(event.get("sourceId") or "") == str(exclude_booking_id)
            ):
                continue
            conflicts.append(
                {
                    "userId": user.get("userId"),
                    "userNickname": user.get("userNickname"),
                    "event": event,
                }
            )
    return conflicts


def _active_source_booking_id() -> int | None:
    """Return the original booking excluded during an UPDATE availability check."""
    source = operation_payload(required=False).get("meeting_source_booking")
    if not isinstance(source, Mapping) or source.get("bookingId") is None:
        return None
    try:
        return int(source["bookingId"])
    except (TypeError, ValueError):
        return None


def _extract_attendee_names(calendar_response: Any, user_ids: list[int]) -> list[str]:
    """按参会人 ID 顺序提取姓名，缺失时用 ID 兜底。"""
    response = calendar_response
    if isinstance(response, Mapping):
        response = response.get("users") or response.get("data") or response.get("items") or []
    by_id = {
        item.get("userId"): item.get("userNickname")
        for item in response
        if isinstance(item, Mapping) and item.get("userId") is not None
    } if isinstance(response, list) else {}
    return [str(by_id.get(user_id) or user_id) for user_id in user_ids]


@tool
def check_meeting_room_conflict(
    meeting_room_id: int,
    start_time: str,
    end_time: str,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """检查指定会议室在时间范围内是否已有预约，只读。"""
    bind_tool_call_id(tool_call_id)
    try:
        start = normalize_local_datetime(start_time)
        end = normalize_local_datetime(end_time)
    except ValueError as exc:
        return tool_failure("INVALID_DATETIME", str(exc))
    writer = get_stream_writer()
    emit(
        writer,
        "tool_started",
        "🔍 正在检查会议室时间冲突……",
        toolName="check_meeting_room_conflict",
        toolCallId=tool_call_id,
    )
    try:
        result = java_post(
            "/agent/tools/meetings/conflict-check",
            {"meetingRoomId": meeting_room_id, "startTime": start, "endTime": end},
        )
    except Exception as exc:
        return _facade_tool_failure(
            writer, "check_meeting_room_conflict", "会议室冲突检查失败，请稍后重试", exc
        )
    emit(
        writer,
        "tool_completed",
        "会议室冲突检查完成",
        toolName="check_meeting_room_conflict",
        toolCallId=tool_call_id,
    )
    return tool_success(result)


@tool
def check_meeting_availability(
    meeting_room_id: int,
    user_ids: list[int],
    start_time: str,
    end_time: str,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """统一检查会议室和参会人日程；有任一冲突时默认禁止生成普通预约草稿。"""
    bind_tool_call_id(tool_call_id)
    blocked = meeting_request_gate(require_ready=True)
    if blocked:
        return blocked
    if not user_ids:
        return tool_failure("INVALID_ARGUMENT", "至少需要一个参会人员")
    try:
        start = normalize_local_datetime(start_time)
        end = normalize_local_datetime(end_time)
    except ValueError as exc:
        return tool_failure("INVALID_DATETIME", str(exc))

    writer = get_stream_writer()
    emit(writer, "tool_started", "🛡️ 正在统一检查会议室和参会人日程可用性……", toolName="check_meeting_availability")
    try:
        ids = list(dict.fromkeys(user_ids))[:20]
        attendee_calendar = java_post_list(
            "/agent/tools/calendar/users",
            {"userIds": ids, "startTime": start, "endTime": end},
        )
        source_booking_id = _active_source_booking_id()
        room_payload = {"meetingRoomId": meeting_room_id, "startTime": start, "endTime": end}
        if source_booking_id is not None:
            room_payload["bookingId"] = source_booking_id
        room_conflict = java_post("/agent/tools/meetings/conflict-check", room_payload)
    except Exception as exc:
        return _facade_tool_failure(writer, "check_meeting_availability", "可预约性检查失败，请稍后重试", exc)

    attendee_conflicts = _extract_attendee_conflicts(attendee_calendar, exclude_booking_id=source_booking_id)
    attendee_names = _extract_attendee_names(attendee_calendar, ids)
    room_conflicts = (
        room_conflict.get("conflicts", [])
        if isinstance(room_conflict, Mapping)
        else []
    )
    fetched_at = datetime.now(timezone.utc)
    expires_at = fetched_at + timedelta(seconds=max(60, int(os.getenv("OA_AGENT_AVAILABILITY_TTL_SECONDS", "1800"))))
    check = {
        "meetingRoomId": meeting_room_id, "userIds": ids, "startTime": start, "endTime": end,
        "sourceBookingId": source_booking_id,
        "attendeeConflicts": attendee_conflicts, "roomConflicts": room_conflicts,
        "attendeeUserNames": attendee_names,
        "fetchedAt": fetched_at.isoformat(),
        "expiresAt": expires_at.isoformat(),
        "refreshPolicy": "required_before_submit",
    }
    source_booking_id = _active_source_booking_id()
    try:
        token = save_availability_check(check)
    except AvailabilityCheckError as exc:
        emit(writer, "tool_failed", "可预约性检查结果保存失败，请稍后重试", toolName="check_meeting_availability", errorCode="AVAILABILITY_STATE_UNAVAILABLE")
        return tool_failure("AVAILABILITY_STATE_UNAVAILABLE", "可预约性检查结果暂时无法保存", details=str(exc))
    can_create = not attendee_conflicts and not room_conflicts
    try:
        persisted = merge_operation_payload({
            "meeting_availability": {**check, "canCreateDraft": can_create},
            "availabilityToken": token,
            "availabilityMessageId": current_agent_context().get("messageId", ""),
            "availabilityRunId": current_agent_context().get("runId", ""),
        })
    except Exception as exc:
        return tool_failure(
            "OPERATION_STATE_SAVE_FAILED",
            "可预约性检查结果保存失败，请稍后重试。",
            details=str(exc), retryable=True,
        )
    operation_id = persisted.operation_id if persisted else current_agent_context().get("operationId", "")
    emit(writer, "tool_completed", "✅ 可预约性检查完成：" + ("无冲突" if can_create else "发现冲突，默认阻止生成普通草稿"), toolName="check_meeting_availability", operationId=operation_id)
    return tool_success({"availabilityToken": token, "canCreateDraft": can_create, "operationId": operation_id, **check})


def check_meeting_availability_batch_service(
    meeting_rooms: list[dict[str, Any]],
    user_ids: list[int],
    start_time: str,
    end_time: str,
    required_capacity: int | None = None,
    tool_call_id: str = "",
) -> ToolResponse:
    """一次检查候选会议室和参会人日程，并确定性返回推荐会议室。

    模型只调用一次这个 Tool；Python 负责统一查询参会人日程、并发检查候选
    会议室、保存每个候选的可预约性 Token，并按容量/输入顺序选择结果。
    """
    bind_tool_call_id(tool_call_id)
    blocked = meeting_request_gate(require_ready=True)
    if blocked:
        return blocked
    if not user_ids or not meeting_rooms:
        return tool_failure("INVALID_ARGUMENT", "至少需要一个参会人和一个候选会议室")
    try:
        start = normalize_local_datetime(start_time)
        end = normalize_local_datetime(end_time)
    except ValueError as exc:
        return tool_failure("INVALID_DATETIME", str(exc))

    writer = get_stream_writer()
    emit(writer, "tool_started", "🛡️ 正在批量检查会议室和参会人日程可用性……", toolName="check_meeting_availability_batch")
    ids = list(dict.fromkeys(user_ids))[:20]
    # During an UPDATE, exclude the source booking from both room and attendee
    # conflict checks. For CREATE there is no source booking and the value is
    # deliberately None.
    source_booking_id = _active_source_booking_id()
    normalized_rooms: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in meeting_rooms[:20]:
        if not isinstance(item, Mapping):
            continue
        raw_id = item.get("meetingRoomId", item.get("id"))
        try:
            room_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if room_id in seen:
            continue
        seen.add(room_id)
        normalized_rooms.append({
            "meetingRoomId": room_id,
            "meetingRoomName": str(item.get("meetingRoomName", item.get("name", "")) or ""),
            "capacity": item.get("capacity", item.get("roomCapacity")),
        })
    if not normalized_rooms:
        return tool_failure("INVALID_ARGUMENT", "候选会议室缺少有效 ID")

    try:
        attendee_calendar = java_post_list(
            "/agent/tools/calendar/users",
            {"userIds": ids, "startTime": start, "endTime": end},
        )
        attendee_conflicts = _extract_attendee_conflicts(attendee_calendar, exclude_booking_id=source_booking_id)
        attendee_names = _extract_attendee_names(attendee_calendar, ids)
        # Keep the authenticated LangGraph context on the calling thread. The
        # model makes one batch Tool Call; Python performs the bounded room
        # checks here without spawning context-less worker threads.
        checks = [_check_room(room["meetingRoomId"], start, end, source_booking_id) for room in normalized_rooms]
    except Exception as exc:
        return _facade_tool_failure(writer, "check_meeting_availability_batch", "批量可预约性检查失败，请稍后重试", exc)

    checked_rooms: list[dict[str, Any]] = []
    for room, room_conflicts in zip(normalized_rooms, checks):
        fetched_at = datetime.now(timezone.utc)
        expires_at = fetched_at + timedelta(seconds=max(60, int(os.getenv("OA_AGENT_AVAILABILITY_TTL_SECONDS", "1800"))))
        check = {
            "meetingRoomId": room["meetingRoomId"],
            "meetingRoomName": room["meetingRoomName"],
            "userIds": ids,
            "startTime": start,
            "endTime": end,
            "sourceBookingId": source_booking_id,
            "attendeeConflicts": attendee_conflicts,
            "roomConflicts": room_conflicts,
            "attendeeUserNames": attendee_names,
            "fetchedAt": fetched_at.isoformat(),
            "expiresAt": expires_at.isoformat(),
            "refreshPolicy": "required_before_submit",
        }
        try:
            token = save_availability_check(check)
        except AvailabilityCheckError as exc:
            emit(writer, "tool_failed", "可预约性检查结果保存失败，请稍后重试", toolName="check_meeting_availability_batch", errorCode="AVAILABILITY_STATE_UNAVAILABLE")
            return tool_failure("AVAILABILITY_STATE_UNAVAILABLE", "可预约性检查结果暂时无法保存", details=str(exc))
        checked_rooms.append({
            **room,
            "availabilityToken": token,
            "canCreateDraft": not attendee_conflicts and not room_conflicts,
            "roomConflicts": room_conflicts,
            "attendeeConflicts": attendee_conflicts,
        })

    eligible = [item for item in checked_rooms if item["canCreateDraft"]]
    recommended = min(eligible, key=lambda item: _room_sort_key(item, required_capacity)) if eligible else None
    persisted = None
    if recommended:
        # Persist the selected room and token beside the already validated
        # meeting_request.  Draft creation must not reconstruct these facts
        # from the model's next Tool Call.
        persisted = merge_operation_payload({
            "meeting_availability": {
                **recommended,
                "canCreateDraft": True,
                "attendeeUserNames": attendee_names,
            },
            "availabilityToken": recommended["availabilityToken"],
            "availabilityMessageId": current_agent_context().get("messageId", ""),
            "availabilityRunId": current_agent_context().get("runId", ""),
            "availabilityCandidates": checked_rooms,
        })
    else:
        # Keep the bounded diagnostic result on the same Operation so the next
        # turn can explain the conflict without creating a thread memory task.
        persisted = merge_operation_payload({
            "availabilityCandidates": checked_rooms,
            "meeting_availability": None,
            "availabilityToken": None,
        })
    operation_id = persisted.operation_id if persisted else current_agent_context().get("operationId", "")
    emit(
        writer,
        "tool_completed",
        "✅ 批量可预约性检查完成：" + (f"推荐{recommended.get('meetingRoomName') or recommended['meetingRoomId']}" if recommended else "暂时没有无冲突会议室"),
        toolName="check_meeting_availability_batch",
        recommendedRoomId=recommended.get("meetingRoomId") if recommended else None,
    )
    return tool_success({
        "rooms": checked_rooms,
        "recommended": recommended,
        "canCreateDraft": recommended is not None,
        "attendeeConflicts": attendee_conflicts,
        "attendeeUserNames": attendee_names,
        "operationId": operation_id,
    })


@tool
def check_meeting_availability_batch(
    meeting_rooms: list[dict[str, Any]], user_ids: list[int], start_time: str,
    end_time: str, required_capacity: int | None = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """Agent adapter for the deterministic availability service."""
    return check_meeting_availability_batch_service(
        meeting_rooms=meeting_rooms, user_ids=user_ids, start_time=start_time,
        end_time=end_time, required_capacity=required_capacity,
        tool_call_id=tool_call_id,
    )


def _check_room(meeting_room_id: int, start_time: str, end_time: str, source_booking_id: int | None = None) -> list[dict[str, Any]]:
    payload = {"meetingRoomId": meeting_room_id, "startTime": start_time, "endTime": end_time}
    if source_booking_id is not None:
        payload["bookingId"] = source_booking_id
    response = java_post(
        "/agent/tools/meetings/conflict-check",
        payload,
    )
    if isinstance(response, Mapping):
        return list(response.get("conflicts", []) or [])
    return []


def _room_sort_key(room: Mapping[str, Any], required_capacity: int | None) -> tuple[Any, ...]:
    capacity = room.get("capacity")
    try:
        value = int(capacity)
    except (TypeError, ValueError):
        value = 10**9
    target = required_capacity or 0
    return (0 if value >= target else 1, abs(value - target), value, str(room.get("meetingRoomName", "")), room["meetingRoomId"])
