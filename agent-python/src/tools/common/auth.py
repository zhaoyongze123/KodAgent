import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from zoneinfo import ZoneInfo

try:
    from langgraph.config import get_config
except ImportError:  # pragma: no cover - console fallback
    get_config = None

LOCAL_AGENT_API_KEY = "kodagent-local-dev-only-20260721"
LOCAL_AGENT_USER_ID = "1"
AGENT_TIMEZONE = ZoneInfo(os.getenv("OA_AGENT_TIMEZONE", "Asia/Shanghai"))


def _java_request_config() -> tuple[str, dict[str, str]]:
    """从当前 LangGraph Run 读取认证上下文，控制台才允许显式开发回退。"""
    base_url = os.getenv("OA_AGENT_BASE_URL", "http://127.0.0.1:48080").rstrip("/")
    # OA_AGENT_DEV_MODE 不再作为全局身份后门。LangGraph Server 必须使用
    # 当前认证上下文中的 identityTicket；固定用户只允许本地控制台调试。
    console_dev_mode = os.getenv("OA_AGENT_CONSOLE_DEV_MODE", "false").lower() == "true"
    agent_key = os.getenv("OA_AGENT_API_KEY")
    if not agent_key:
        if console_dev_mode:
            agent_key = LOCAL_AGENT_API_KEY
        else:
            raise RuntimeError("缺少 OA_AGENT_API_KEY，已拒绝使用内置开发密钥")
    identity_ticket = None
    context_user_id = None
    context_tenant_id = None
    metadata = {}
    if get_config is not None:
        try:
            config = get_config()
            metadata = config.get("metadata") or {}
            identity_ticket = metadata.get("identityTicket") or metadata.get("identity_ticket")
            context_user_id = metadata.get("userId") or metadata.get("user_id")
            context_tenant_id = metadata.get("tenantId") or metadata.get("tenant_id")
            # Some LangGraph runtime versions preserve the authorization owner
            # but intentionally omit arbitrary auth fields from run metadata.
            # The owner is stamped by auth.py and is safe to use as a scoped
            # identity source after validating its shape.
            owner = metadata.get("owner")
            if (not context_user_id or not context_tenant_id) and isinstance(owner, str) and ":" in owner:
                owner_tenant, owner_user = owner.split(":", 1)
                if owner_tenant.isdigit() and owner_user.isdigit():
                    context_tenant_id = context_tenant_id or owner_tenant
                    context_user_id = context_user_id or owner_user
        except RuntimeError:
            pass
    identity_ticket = identity_ticket or os.getenv("OA_AGENT_IDENTITY")
    dev_user_id = os.getenv("OA_AGENT_USER_ID") or LOCAL_AGENT_USER_ID

    headers = {"X-Agent-Key": agent_key}
    if identity_ticket:
        headers["X-Agent-Identity"] = identity_ticket
    elif context_user_id and context_tenant_id:
        # The LangGraph server has already authenticated the request. Create a
        # short-lived service-to-facade ticket when the runtime does not carry
        # the original ticket into the Tool RunnableConfig. Java verifies the
        # same HMAC secret and still re-checks the user and tenant.
        headers["X-Agent-Identity"] = _issue_internal_ticket(
            str(context_user_id), str(context_tenant_id)
        )
    elif console_dev_mode and dev_user_id:
        headers["X-Agent-User-Id"] = dev_user_id
    else:
        raise RuntimeError("缺少当前 Run 的 OA_AGENT_IDENTITY，已拒绝使用固定用户身份")
    # Do not mirror per-request identity into ``os.environ``.  Environment
    # variables are process-global and a LangGraph worker can serve multiple
    # tenants concurrently.  The scoped identity is already carried by the
    # request headers and the current RunnableConfig metadata above.
    return base_url, headers


def _java_request_config_for_identity(identity: tuple[str, str]) -> tuple[str, dict[str, str]]:
    """Build Java headers from a persisted event identity for Outbox replay."""
    user_id, tenant_id = identity
    base_url = os.getenv("OA_AGENT_BASE_URL", "http://127.0.0.1:48080").rstrip("/")
    agent_key = os.getenv("OA_AGENT_API_KEY")
    if not agent_key:
        raise RuntimeError("缺少 OA_AGENT_API_KEY，已拒绝使用内置开发密钥")
    return base_url, {
        "X-Agent-Key": agent_key,
        "X-Agent-Identity": _issue_internal_ticket(user_id, tenant_id),
    }


def _issue_internal_ticket(user_id: str, tenant_id: str) -> str:
    """Issue a short-lived ticket for the trusted LangGraph -> Java hop."""
    secret = os.getenv("OA_AGENT_IDENTITY_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("OA_AGENT_IDENTITY_SECRET 未配置或长度不足 32 位")
    now = int(time.time())
    payload = {
        "userId": int(user_id) if str(user_id).isdigit() else str(user_id),
        "tenantId": int(tenant_id) if str(tenant_id).isdigit() else str(tenant_id),
        "issuedAt": now,
        "expiresAt": now + 120,
        "nonce": str(uuid.uuid4()),
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    ).decode().rstrip("=")
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
    return encoded + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")
