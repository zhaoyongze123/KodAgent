import atexit
import json
import os
import re
import threading
import time
from datetime import datetime
from typing import Any

import httpx

from .auth import AGENT_TIMEZONE, _java_request_config, _java_request_config_for_identity
from .contracts import get_tool_contract, redact_sensitive
from ...domain.errors import describe_error_code


_RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


class JavaFacadeBusinessError(RuntimeError):
    """A Java Facade business error returned inside an HTTP 200 envelope."""

    def __init__(self, code: int | str, message: str, payload: dict[str, Any], path: str = ""):
        self.code = code
        self.message = message
        self.payload = payload
        self.path = path
        descriptor = describe_error_code(str(code))
        self.error_code = descriptor.code
        self.kind = descriptor.kind
        self.retryable = descriptor.retryable
        super().__init__(f"Java Facade business error {code}: {message}")


class JavaFacadeConnectionError(RuntimeError):
    """The Java Facade could not be reached after the configured retries."""

    error_code = "JAVA_FACADE_CONNECTION_FAILED"
    kind = "dependency"
    retryable = True


class JavaFacadeHttpError(RuntimeError):
    """The Java Facade returned a non-success HTTP status."""

    def __init__(self, status_code: int, path: str):
        self.status_code = status_code
        self.path = path
        self.error_code = f"JAVA_FACADE_HTTP_{status_code}"
        self.kind = "authorization" if status_code in {401, 403} else "dependency" if status_code in _RETRYABLE_HTTP_STATUSES else "internal"
        self.retryable = status_code in _RETRYABLE_HTTP_STATUSES
        super().__init__(f"Java Facade HTTP {status_code}: {path}")


class JavaFacadeJsonDecodeError(RuntimeError):
    """The Java Facade response body was not valid JSON."""

    def __init__(self, status_code: int, content_type: str | None, path: str = ""):
        self.status_code = status_code
        self.content_type = content_type
        self.path = path
        self.error_code = "JAVA_FACADE_INVALID_JSON"
        self.kind = "dependency"
        self.retryable = False
        super().__init__("Java Facade 返回值不是有效 JSON")


class JavaFacadeResponseTypeError(RuntimeError):
    """The response JSON type is outside the endpoint contract."""

    def __init__(self, path: str, expected_type: str, actual_type: str):
        self.path = path
        self.expected_type = expected_type
        self.actual_type = actual_type
        self.error_code = "JAVA_FACADE_RESPONSE_TYPE_INVALID"
        self.kind = "dependency"
        self.retryable = False
        super().__init__(
            f"Java Facade 返回值类型不符合契约：{path} expected={expected_type} actual={actual_type}"
        )


# ``httpx.request`` creates a short-lived transport for every call.  Keep the
# transport process-local and initialize it lazily: a module-level client
# created before a pre-fork worker starts could otherwise carry inherited
# sockets into the child process.  httpx.Client is safe to share between
# threads; the PID check gives each worker its own pool.
_HTTP_CLIENT_LOCK = threading.RLock()
_SHARED_HTTP_CLIENT: httpx.Client | None = None
_SHARED_HTTP_CLIENT_PID: int | None = None


def _new_http_client() -> httpx.Client:
    return httpx.Client(
        timeout=30.0,
        limits=httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=30.0,
        ),
    )


def _get_shared_http_client() -> httpx.Client:
    """Return the current worker's shared synchronous transport client."""
    global _SHARED_HTTP_CLIENT, _SHARED_HTTP_CLIENT_PID
    pid = os.getpid()
    with _HTTP_CLIENT_LOCK:
        if _SHARED_HTTP_CLIENT is not None and _SHARED_HTTP_CLIENT_PID == pid:
            return _SHARED_HTTP_CLIENT
        previous = _SHARED_HTTP_CLIENT
        _SHARED_HTTP_CLIENT = _new_http_client()
        _SHARED_HTTP_CLIENT_PID = pid
        if previous is not None:
            # A forked child owns a separate descriptor table.  Closing the
            # inherited copy here does not close the parent's client.
            previous.close()
        return _SHARED_HTTP_CLIENT


def _close_shared_http_client() -> None:
    global _SHARED_HTTP_CLIENT, _SHARED_HTTP_CLIENT_PID
    with _HTTP_CLIENT_LOCK:
        client = _SHARED_HTTP_CLIENT
        _SHARED_HTTP_CLIENT = None
        _SHARED_HTTP_CLIENT_PID = None
        if client is not None:
            client.close()


atexit.register(_close_shared_http_client)


def normalize_local_datetime(value: str) -> str:
    """将模型可能生成的 ISO 时间统一为 Java Facade 要求的本地时间格式。"""
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"时间格式无效：{value}，请使用 yyyy-MM-dd HH:mm:ss") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(AGENT_TIMEZONE).replace(tzinfo=None)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def _tool_name_for_path(path: str, method: str = "GET") -> str:
    """Resolve a Java Facade path to its internal tool contract.

    The table is deliberately method-aware.  Several Java resources share a
    prefix while exposing different read/write operations (for example batch
    approval preview versus decision, and personal-schedule detail versus
    draft creation).  Exact routes are checked before dynamic prefixes so a
    resource named ``my`` or ``drafts`` can never be mistaken for an ID.
    """
    method = method.upper()

    # Keep this registry as the single Python -> Java Facade boundary.  The
    # Java controllers intentionally expose a few resources with the same
    # prefix (for example personal-schedule details and drafts), so matching
    # by ``startswith`` is unsafe: an unknown suffix can silently receive a
    # different tool contract and permission.  Exact routes are checked first
    # and the dynamic patterns below require the complete expected path shape.
    exact_routes = {
        ("GET", "/agent/tools/meetings/rooms"): "list_available_meeting_rooms",
        ("GET", "/agent/tools/meetings/my"): "list_my_meeting_bookings",
        ("GET", "/agent/tools/meetings/report"): "meeting_report",
        ("GET", "/agent/tools/meetings/book/status"): "get_meeting_booking_commit_status",
        ("GET", "/agent/tools/calendar/personal-schedules/commit/status"): "get_personal_schedule_commit_status",
        ("GET", "/agent/tools/party-files/commit/status"): "get_party_file_commit_status",
        ("POST", "/agent/tools/meetings/conflict-check"): "check_meeting_room_conflict",
        ("POST", "/agent/tools/meetings/book"): "confirm_meeting_booking",
        ("GET", "/agent/tools/users/search"): "search_meeting_attendees",
        ("GET", "/agent/tools/users/me"): "get_current_meeting_user",
        ("POST", "/agent/tools/calendar/users"): "get_meeting_attendees_calendar",
        ("GET", "/agent/tools/calendar/my"): "get_my_calendar",
        ("GET", "/agent/tools/calendar/report"): "schedule_report",
        ("POST", "/agent/tools/calendar/personal-schedules/drafts"): "create_personal_schedule_draft",
        ("POST", "/agent/tools/calendar/personal-schedules/commit"): "confirm_personal_schedule",
        ("GET", "/agent/tools/approvals/types"): "list_startable_approval_types",
        ("GET", "/agent/tools/approvals/insights"): "analyze_my_pending_approvals",
        ("GET", "/agent/tools/approvals/applications"): "list_my_approval_applications",
        ("GET", "/agent/tools/approvals/history"): "list_my_approval_history",
        ("GET", "/agent/tools/approvals/report"): "approval_report",
        ("GET", "/agent/tools/approvals/inbox"): "search_my_pending_approvals",
        ("POST", "/agent/tools/approvals/preview"): "preview_approval_request",
        ("POST", "/agent/tools/approvals/request-draft"): "create_approval_request_draft",
        ("POST", "/agent/tools/approvals/request-commit"): "confirm_approval_request_action",
        ("POST", "/agent/tools/approvals/generic/draft"): "create_generic_approval_request_draft",
        ("POST", "/agent/tools/approvals/generic/commit"): "confirm_approval_request_action",
        ("POST", "/agent/tools/approvals/withdraw-draft"): "create_approval_withdraw_draft",
        ("POST", "/agent/tools/approvals/withdraw-commit"): "confirm_approval_withdraw_action",
        ("POST", "/agent/tools/approvals/batch/preview"): "preview_approval_batch_action",
        ("POST", "/agent/tools/approvals/batch/execute"): "confirm_approval_batch_action",
        ("GET", "/agent/tools/tasks/todo"): "list_my_pending_approvals",
        ("POST", "/agent/tools/tasks/action-preview"): "preview_approval_task_action",
        ("POST", "/agent/tools/tasks/action-execute"): "confirm_approval_task_action",
        ("POST", "/agent/tools/tasks/action-reconcile"): "reconcile_approval_task_action",
        ("GET", "/agent/tools/tasks/action-status"): "get_approval_task_action_status",
        ("GET", "/agent/tools/party-knowledge/search"): "search_party_knowledge",
        ("POST", "/agent/tools/party-knowledge/search"): "search_party_knowledge",
        ("GET", "/agent/tools/party-knowledge/health"): "check_party_knowledge_health",
        ("POST", "/agent/tools/party-files/query-plan"): "execute_party_file_metadata_plan",
        ("GET", "/agent/tools/party-files/report"): "party_file_report",
        ("GET", "/agent/tools/party-files/my-page"): "search_party_files",
        ("GET", "/agent/tools/party-files/my-get"): "get_party_file_detail",
        ("GET", "/agent/tools/party-files/my-attachment"): "get_party_file_attachment",
        ("GET", "/agent/tools/party-files/categories"): "list_party_file_categories",
        ("POST", "/agent/tools/party-files/commit/create"): "confirm_create_party_file",
        ("POST", "/agent/tools/party-files/commit/update"): "confirm_update_party_file",
        ("POST", "/agent/tools/party-files/commit/delete"): "confirm_delete_party_file",
        ("GET", "/agent/tools/projects"): "list_accessible_projects",
        # 附件是领域无关的受控交付能力。必须在传输白名单登记，才能带着它的
        # 独立权限和幂等约束进入 Java；不能把它伪装成任一项目报告接口。
        ("POST", "/agent/artifacts"): "create_document_artifact",
        ("POST", "/agent/drafts/meeting-booking"): "create_meeting_booking_draft",
        ("GET", "/agent/config/resolve"): "resolve_agent_model",
        ("GET", "/agent/config/models"): "list_agent_models",
        ("GET", "/agent/config/actions"): "get_agent_action_catalog",
    }
    exact = exact_routes.get((method, path))
    if exact:
        return exact

    dynamic_routes = (
        # Draft routes must be checked before the one-segment detail route;
        # the trailing ``/status`` is part of a different Java operation.
        ("POST", r"^/agent/drafts/meeting-booking/[^/]+/status$", "update_meeting_booking_draft_status"),
        ("GET", r"^/agent/drafts/meeting-booking/[^/]+$", "get_meeting_booking_draft"),
        ("DELETE", r"^/agent/drafts/meeting-booking/[^/]+$", "delete_meeting_booking_draft"),
        ("GET", r"^/agent/config/models/[0-9]+$", "resolve_agent_model"),
        ("GET", r"^/agent/tools/meetings/[0-9]+$", "get_my_meeting_booking"),
        ("GET", r"^/agent/tools/party-knowledge/documents/[0-9]+$", "get_party_knowledge_document"),
        ("GET", r"^/agent/tools/party-knowledge/chunks/[0-9]+$", "get_party_knowledge_chunk"),
        ("GET", r"^/agent/tools/calendar/personal-schedules/drafts/[^/]+$", "get_personal_schedule_draft"),
        ("GET", r"^/agent/tools/calendar/personal-schedules/[0-9]+$", "get_personal_schedule"),
        ("GET", r"^/agent/tools/party-files/manage/[0-9]+$", "get_manage_party_file"),
        ("POST", r"^/agent/tools/party-files/drafts/create$", "create_party_file_draft"),
        ("POST", r"^/agent/tools/party-files/drafts/update$", "update_party_file_draft"),
        ("POST", r"^/agent/tools/party-files/drafts/delete$", "delete_party_file_draft"),
        ("GET", r"^/agent/tools/projects/[^/]+/snapshot$", "get_project_snapshot"),
        ("GET", r"^/agent/tools/projects/[^/]+/tasks$", "get_project_tasks"),
        ("GET", r"^/agent/tools/projects/[^/]+/activity$", "get_project_activity"),
        ("GET", r"^/agent/tools/projects/[^/]+/documents$", "get_project_documents"),
        ("GET", r"^/agent/tools/projects/[^/]+/analysis$", "analyze_project"),
        ("POST", r"^/agent/tools/projects/[^/]+/knowledge/search$", "search_project_knowledge"),
        ("POST", r"^/agent/artifacts$", "create_document_artifact"),
        ("GET", r"^/agent/artifacts/[^/]+/download$", "download_document_artifact"),
        ("GET", r"^/agent/tools/party-files/drafts/[^/]+$", "get_party_file_draft"),
        ("GET", r"^/agent/tools/approvals/batch/[^/]+$", "preview_approval_batch_action"),
        ("GET", r"^/agent/tools/approvals/applications/[^/]+$", "get_my_approval_application"),
        ("POST", r"^/agent/tools/approvals/batch/[^/]+/(?i:approve|reject|cancel)$", "confirm_approval_batch_action"),
        ("POST", r"^/agent/tools/approvals/batch/[^/]+/reconcile$", "reconcile_approval_batch_action"),
        ("GET", r"^/agent/tools/tasks/[^/]+$", "get_approval_task_detail"),
        # AgentApprovalController owns a shared, owner-scoped confirmation
        # record. Keep its nested card paths distinct from the plain id path.
        ("GET", r"^/agent/approvals/pending-card/by-draft/[^/]+$", "get_meeting_booking_approval"),
        ("GET", r"^/agent/approvals/[^/]+/pending-card$", "get_meeting_booking_approval"),
        ("GET", r"^/agent/approvals/[^/]+$", "get_meeting_booking_approval"),
        ("POST", r"^/agent/approvals/[^/]+/(?i:approve|reject|resume)$", "decide_agent_approval"),
        ("POST", r"^/agent/runs/[^/]+/events$", "agent_event_persist"),
        ("GET", r"^/agent/runs/[^/]+/events$", "get_agent_run_events"),
        ("POST", r"^/agent/runs/[^/]+/cancel$", "cancel_agent_run"),
        ("POST", r"^/agent/runs/[^/]+/metrics$", "record_agent_run_metric"),
        ("GET", r"^/agent/threads/[^/]+/events$", "get_agent_thread_events"),
    )
    for route_method, pattern, name in dynamic_routes:
        if method == route_method and re.fullmatch(pattern, path):
            return name
    raise RuntimeError(f"未登记 Java Facade 路径，拒绝调用：{path}")


def _request(method: str, path: str, *, payload: dict[str, Any] | None = None,
             params: dict[str, Any] | None = None,
             identity: tuple[str, str] | None = None) -> httpx.Response:
    base_url, headers = _java_request_config() if identity is None else _java_request_config_for_identity(identity)
    tool_name = _tool_name_for_path(path, method)
    contract = get_tool_contract(tool_name)
    # A retry after a server-side timeout can arrive after Java has accepted a
    # write.  Read-only contracts are safe to retry; side-effecting contracts
    # need an explicit idempotency contract before they may retry.
    can_retry = bool(contract.retryable) and (
        contract.read_only or str(contract.idempotency or "none").lower() != "none"
    )
    attempts = contract.max_retries if can_retry else 0
    for attempt in range(attempts + 1):
        try:
            request_headers = {
                **headers,
                "X-Agent-Tool": tool_name,
                "X-Agent-Permission": contract.permission,
            }
            response = _get_shared_http_client().request(
                method,
                f"{base_url}{path}",
                params=params,
                json=payload,
                headers=request_headers,
                timeout=contract.timeout_seconds,
            )
            if response.status_code not in _RETRYABLE_HTTP_STATUSES or attempt >= attempts:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise JavaFacadeHttpError(response.status_code, path) from exc
                return response
        except JavaFacadeHttpError:
            raise
        except httpx.RequestError as exc:
            if attempt >= attempts:
                raise JavaFacadeConnectionError(f"Java Facade 连接失败：{path}") from exc
        time.sleep(min(0.25 * (2 ** attempt), 2.0))
    raise RuntimeError(f"Tool 请求未返回结果: {tool_name}")


def java_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return _decode_json_or_empty(_request("GET", path, params=params), path=path, expected_type="object")


def java_post(path: str, payload: dict[str, Any], *, identity: tuple[str, str] | None = None) -> dict[str, Any]:
    return _decode_json_or_empty(
        _request("POST", path, payload=payload, identity=identity),
        path=path,
        expected_type="object",
    )


def java_get_list(path: str, params: dict[str, Any] | None = None) -> list[Any]:
    return _decode_json_or_empty(_request("GET", path, params=params), path=path, expected_type="list")


def java_post_list(
    path: str,
    payload: dict[str, Any],
    *,
    identity: tuple[str, str] | None = None,
) -> list[Any]:
    return _decode_json_or_empty(
        _request("POST", path, payload=payload, identity=identity),
        path=path,
        expected_type="list",
    )


def _decode_json_or_empty(
    response: httpx.Response,
    *,
    path: str = "<direct response>",
    expected_type: str = "object",
) -> dict[str, Any] | list[Any]:
    """兼容 Java void/204 接口的空响应。

    业务接口大多数返回 JSON，但状态更新、删除等接口可能正常返回
    204 No Content。空响应不是错误，统一转换为空对象，避免在业务已
    成功后因为 ``response.json()`` 解析空字符串而让 Agent 失败。
    """
    if not response.content or not response.content.strip():
        return [] if expected_type == "list" else {}
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise JavaFacadeJsonDecodeError(
            response.status_code, response.headers.get("content-type"), path
        ) from exc
    if isinstance(payload, dict) and "code" in payload:
        code = payload.get("code")
        try:
            success = int(code) in {0, 200}
        except (TypeError, ValueError):
            success = False
        if not success:
            message = str(payload.get("msg") or payload.get("message") or "Java 业务处理失败")
            raise JavaFacadeBusinessError(code, message, payload, path)
    actual_type = "object" if isinstance(payload, dict) else "list" if isinstance(payload, list) else type(payload).__name__
    if expected_type == "object" and not isinstance(payload, dict):
        raise JavaFacadeResponseTypeError(path, expected_type, actual_type)
    if expected_type == "list" and not isinstance(payload, list):
        raise JavaFacadeResponseTypeError(path, expected_type, actual_type)
    return payload


def persist_agent_event(event: dict[str, Any], *, require_persist: bool = False) -> dict[str, Any]:
    """Write a Java Run event synchronously.

    Runtime Operation/Effect facts use the PostgreSQL Runtime Outbox.  This
    path is reserved for Java's Run event projection and must not create a
    second process-local retry database.
    """
    safe_event = redact_sensitive(event, ("apiKey", "identityTicket", "authorization", "token"))
    try:
        event_identity = None
        if event.get("userId") is not None and event.get("tenantId") is not None:
            event_identity = (str(event["userId"]), str(event["tenantId"]))
        response = java_post(
            f"/agent/runs/{event['runId']}/events",
            safe_event,
            identity=event_identity,
        )
        # Controllers are commonly wrapped by the platform's CommonResult;
        # direct tests and internal deployments may return the body itself.
        if isinstance(response.get("data"), dict):
            return response["data"]
        return response
    except Exception:
        if require_persist:
            raise
        return {}


def save_meeting_draft(draft: dict[str, Any]) -> dict[str, Any]:
    return java_post("/agent/drafts/meeting-booking", draft)


def get_meeting_draft(draft_id: str) -> dict[str, Any]:
    return java_get(f"/agent/drafts/meeting-booking/{draft_id}")


def get_meeting_booking_commit_status(
    draft_id: str,
    approval_id: str,
    operation_id: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "draftId": draft_id,
        "approvalId": approval_id,
    }
    if operation_id:
        params["operationId"] = operation_id
    return java_get("/agent/tools/meetings/book/status", params)


def get_personal_schedule_commit_status(
    draft_id: str,
    approval_id: str,
    operation_id: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "draftId": draft_id,
        "approvalId": approval_id,
    }
    if operation_id:
        params["operationId"] = operation_id
    return java_get("/agent/tools/calendar/personal-schedules/commit/status", params)


def get_party_file_commit_status(
    draft_id: str,
    approval_id: str,
    operation_id: str,
) -> dict[str, Any]:
    return java_get(
        "/agent/tools/party-files/commit/status",
        {"draftId": draft_id, "approvalId": approval_id, "operationId": operation_id},
    )


def get_approval_task_action_status(approval_id: str, operation_id: str) -> dict[str, Any]:
    return java_get(
        "/agent/tools/tasks/action-status",
        {"approvalId": approval_id, "operationId": operation_id},
    )


def reconcile_approval_task_action(approval_id: str, operation_id: str) -> dict[str, Any]:
    return java_post(
        "/agent/tools/tasks/action-reconcile",
        {"approvalId": approval_id, "operationId": operation_id},
    )


def get_meeting_approval(approval_id: str) -> dict[str, Any]:
    return java_get(f"/agent/approvals/{approval_id}")


def delete_meeting_draft(draft_id: str) -> None:
    _request("DELETE", f"/agent/drafts/meeting-booking/{draft_id}")


def update_meeting_draft_status(draft_id: str, status: str) -> None:
    java_post(f"/agent/drafts/meeting-booking/{draft_id}/status", {"status": status})


def resolve_agent_model(model_id: str | None = None, agent_name: str = "oa-main-agent") -> dict[str, Any]:
    """解析本次 Run 模型；显式 model_id 为空时读取 Java 侧默认绑定。"""
    if model_id:
        return java_get(f"/agent/config/models/{model_id}")
    return java_get("/agent/config/resolve", {"agentName": agent_name})


def get_agent_action_catalog() -> dict[str, Any]:
    """Read the Java-owned action contract for the current OA identity."""
    return java_get("/agent/config/actions")


def as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
