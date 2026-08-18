"""预约可用性检查的短期、跨进程状态。"""

import json
import os
from secrets import token_urlsafe
from typing import Any

from redis import Redis

from ..common.events import current_agent_context


class AvailabilityCheckError(RuntimeError):
    """可用性检查状态不存在、已过期或无法访问。"""


_REDIS: Redis | None = None


def _redis() -> Redis:
    global _REDIS
    if _REDIS is None:
        _REDIS = Redis.from_url(
            os.getenv("OA_AGENT_REDIS_URL", "redis://127.0.0.1:16379/0"),
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
    return _REDIS


def _key(token: str) -> str:
    return f"kodagent:meeting:availability:{token}"


def save_availability_check(check: dict[str, Any]) -> str:
    """保存检查结果，默认 30 分钟过期；不再使用进程内字典。"""
    context = current_agent_context()
    token = token_urlsafe(32)
    value = {
        **check,
        "token": token,
        "runId": context["runId"],
        "threadId": context["threadId"],
        "tenantId": context["tenantId"],
        "userId": context["userId"],
        "createdMessageId": context["messageId"],
    }
    ttl = max(60, int(os.getenv("OA_AGENT_AVAILABILITY_TTL_SECONDS", "1800")))
    try:
        if not _redis().set(_key(token), json.dumps(value, ensure_ascii=False), ex=ttl, nx=True):
            raise AvailabilityCheckError("可预约性检查 Token 生成冲突，请重试")
    except AvailabilityCheckError:
        raise
    except Exception as exc:
        raise AvailabilityCheckError(f"Redis 不可用，无法保存可预约性检查：{exc}") from exc
    return token


def get_availability_check(token: str, *, meeting_room_id: int, user_ids: list[int],
                           start_time: str, end_time: str) -> dict[str, Any]:
    """读取并校验检查结果，防止跨用户、跨 Thread 或参数复用。"""
    if not token:
        raise AvailabilityCheckError("缺少可预约性检查 Token")
    try:
        raw = _redis().get(_key(token))
    except Exception as exc:
        raise AvailabilityCheckError(f"Redis 不可用，无法读取可预约性检查：{exc}") from exc
    if not raw:
        raise AvailabilityCheckError("可预约性检查已过期或不存在，请重新检查")
    try:
        check = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AvailabilityCheckError("可预约性检查数据损坏，请重新检查") from exc

    context = current_agent_context()
    expected = {
        "meetingRoomId": meeting_room_id,
        "userIds": user_ids,
        "startTime": start_time,
        "endTime": end_time,
        "runId": context["runId"],
        "threadId": context["threadId"],
        "tenantId": context["tenantId"],
        "userId": context["userId"],
        "createdMessageId": context["messageId"],
    }
    for field, value in expected.items():
        if check.get(field) != value:
            raise AvailabilityCheckError(f"检查结果与当前预约参数或身份不匹配：{field}")
    return check
