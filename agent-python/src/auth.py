"""LangGraph Server authentication for the OA Agent.

KodBox/OA issues a short-lived HMAC identity ticket.  LangGraph validates the
ticket before a thread or run is accepted, and copies the verified identity
into run metadata. Java still validates the same ticket again on every
business-tool request.
"""

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from langgraph_sdk import Auth

auth = Auth()


def _header(headers: dict[bytes, bytes] | None, name: str) -> str | None:
    if not headers:
        return None
    wanted = name.lower().encode()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value.decode("utf-8", errors="replace")
    return None


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _verify_ticket(ticket: str) -> dict[str, Any]:
    secret = os.getenv("OA_AGENT_IDENTITY_SECRET") or os.getenv("OA_AGENT_API_KEY", "")
    if len(secret) < 32:
        raise Auth.exceptions.HTTPException(503, "OA_AGENT_IDENTITY_SECRET 未配置或长度不足 32 位")
    parts = ticket.split(".", 1)
    if len(parts) != 2:
        raise Auth.exceptions.HTTPException(401, "Agent 身份票据格式无效")
    payload_part, signature_part = parts
    expected = hmac.new(secret.encode(), payload_part.encode(), hashlib.sha256).digest()
    try:
        actual = _decode(signature_part)
        payload = json.loads(_decode(payload_part))
    except (ValueError, json.JSONDecodeError) as exc:
        raise Auth.exceptions.HTTPException(401, "Agent 身份票据内容无效") from exc
    if not hmac.compare_digest(expected, actual):
        raise Auth.exceptions.HTTPException(401, "Agent 身份票据签名无效")
    now = int(time.time())
    if payload.get("expiresAt", 0) <= now or payload.get("issuedAt", 0) > now + 30:
        raise Auth.exceptions.HTTPException(401, "Agent 身份票据已过期或尚未生效")
    if not payload.get("userId") or not payload.get("tenantId"):
        raise Auth.exceptions.HTTPException(401, "Agent 身份票据缺少用户或租户")
    return payload


@auth.authenticate
async def authenticate(headers: dict[bytes, bytes] | None = None) -> dict[str, Any]:
    ticket = _header(headers, "x-agent-identity")
    if not ticket:
        raise Auth.exceptions.HTTPException(401, "缺少 X-Agent-Identity 用户身份票据")
    payload = _verify_ticket(ticket)
    tenant_id = str(payload["tenantId"])
    user_id = str(payload["userId"])
    return {
        "identity": f"{tenant_id}:{user_id}",
        "display_name": f"oa-user-{user_id}",
        "permissions": [],
        "userId": user_id,
        "tenantId": tenant_id,
        "identityTicket": ticket,
    }


def _stamp_metadata(ctx: Any, value: Any) -> bool:
    if not isinstance(value, dict):
        return True
    user = ctx.user
    metadata = value.setdefault("metadata", {})
    metadata["userId"] = user.get("userId")
    metadata["tenantId"] = user.get("tenantId")
    metadata["identityTicket"] = user.get("identityTicket")
    metadata["owner"] = user.identity
    return True


@auth.on
async def stamp_run_identity(ctx: Auth.types.AuthContext, value: Any) -> bool:
    return _stamp_metadata(ctx, value)


@auth.on.threads.create_run
async def stamp_create_run_identity(ctx: Auth.types.AuthContext, value: Any) -> bool:
    """Carry the authenticated OA identity into the graph run metadata.

    LangGraph chooses the most specific authorization handler.  The generic
    ``@auth.on`` handler therefore does not run for ``threads.create_run``
    once a resource-specific handler exists.  Without this explicit handler,
    the graph can authenticate the browser request and create the thread but
    the worker loses ``userId``/``tenantId``/``identityTicket``; the first Java
    Facade call then becomes an unexplained 401.  Stamping the run is the
    single boundary where the verified identity is transferred into the
    graph execution context.
    """
    return _stamp_metadata(ctx, value)


@auth.on.threads.create
async def create_thread(ctx: Auth.types.AuthContext, value: Any) -> bool:
    return _stamp_metadata(ctx, value)


@auth.on.threads.read
async def read_threads(ctx: Auth.types.AuthContext, value: Any) -> dict[str, Any]:
    return {"owner": ctx.user.identity}


@auth.on.threads.search
async def search_threads(ctx: Auth.types.AuthContext, value: Any) -> dict[str, Any]:
    return {"owner": ctx.user.identity}


@auth.on.threads.delete
async def delete_thread(ctx: Auth.types.AuthContext, value: Any) -> dict[str, Any]:
    return {"owner": ctx.user.identity}
