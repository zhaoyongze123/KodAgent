#!/usr/bin/env python3
"""Repeatable, non-production-code fault acceptance for KodAgent.

The default mode is a dry-run.  ``--live`` enables dependency probes and the
Runtime PostgreSQL fixture.  A real Flowable action is *still* opt-in through
``--action-execute`` and requires an existing, user-supplied approved action.
This script never creates an approval or discovers one from the inbox.

The report is deliberately metadata-only: response bodies, credentials,
identity tickets, request payloads and provider error text are never printed.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import socket
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent-python"))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / "agent-python" / ".env")
except Exception:
    pass


SENSITIVE = re.compile(r"(?i)(authorization|x-agent-key|x-agent-identity|api[-_ ]?key|token|secret|password)\s*[:=]\s*[^,; ]+")
URL_CREDENTIALS = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^/@\s:]+:[^/@\s]+@")


def safe_error(exc: BaseException) -> str:
    text = re.sub(SENSITIVE, r"\1=<redacted>", str(exc))
    text = URL_CREDENTIALS.sub(r"\1<redacted>@", text)
    for name in ("OA_AGENT_API_KEY", "OA_AGENT_IDENTITY", "OA_AGENT_IDENTITY_SECRET"):
        value = os.getenv(name)
        if value:
            text = text.replace(value, "<redacted>")
    return text[:240]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def result(status: str, **details: object) -> dict[str, object]:
    return {"status": status, **details}


def java_headers() -> dict[str, str]:
    """Build the same short-lived HMAC ticket using only stdlib imports."""
    key = os.getenv("OA_AGENT_API_KEY")
    user = os.getenv("OA_AGENT_USER_ID", "1")
    tenant = os.getenv("OA_AGENT_TENANT_ID", "1")
    secret = os.getenv("OA_AGENT_IDENTITY_SECRET", "")
    if not key:
        raise RuntimeError("OA_AGENT_API_KEY is not configured")
    if len(secret) < 32:
        raise RuntimeError("OA_AGENT_IDENTITY_SECRET is not configured")
    payload = {
        "userId": int(user) if str(user).isdigit() else str(user),
        "tenantId": int(tenant) if str(tenant).isdigit() else str(tenant),
        "issuedAt": int(time.time()),
        "expiresAt": int(time.time()) + 120,
        "nonce": str(uuid.uuid4()),
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
    ticket = encoded + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return {
        "Content-Type": "application/json",
        "X-Agent-Key": key,
        "X-Agent-Identity": ticket,
    }


def http_call(base_url: str, method: str, path: str, *, params: dict[str, str] | None = None,
              payload: dict[str, object] | None = None, timeout: float = 5.0,
              tool_name: str, permission: str) -> dict[str, object]:
    url = base_url.rstrip("/") + path
    if params:
        url += "?" + urlencode(params)
    body = json.dumps(payload).encode() if payload is not None else None
    try:
        headers = java_headers()
    except Exception as exc:
        return result("BLOCKED", reason="Java authentication is not configured", errorClass=type(exc).__name__)
    headers["X-Agent-Tool"] = tool_name
    headers["X-Agent-Permission"] = permission
    request = Request(url, data=body, method=method, headers=headers)
    started = time.monotonic()
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            parsed: object = json.loads(raw) if raw else None
            return result("OK", httpStatus=response.status, elapsedMs=round((time.monotonic() - started) * 1000), responseKeys=sorted(parsed) if isinstance(parsed, dict) else [])
    except HTTPError as exc:
        return result("HTTP_ERROR", httpStatus=exc.code, elapsedMs=round((time.monotonic() - started) * 1000))
    except (TimeoutError, socket.timeout):
        return result("TIMEOUT", elapsedMs=round((time.monotonic() - started) * 1000))
    except (URLError, OSError) as exc:
        return result("UNAVAILABLE", errorClass=type(exc).__name__)
    except json.JSONDecodeError:
        return result("INVALID_JSON", elapsedMs=round((time.monotonic() - started) * 1000))


def http_json_call(base_url: str, method: str, path: str, *,
                   payload: dict[str, object] | None = None,
                   tool_name: str, permission: str,
                   timeout: float = 10.0) -> dict[str, object]:
    """Call Java and retain the decoded body only inside this process.

    The returned report never includes the body. This helper exists for the
    multi-step batch acceptance where previewId and confirmationToken must be
    passed to the next real endpoint without printing either value.
    """
    url = base_url.rstrip("/") + path
    body = json.dumps(payload).encode() if payload is not None else None
    try:
        headers = java_headers()
    except Exception as exc:
        return result("BLOCKED", reason="Java authentication is not configured", errorClass=type(exc).__name__)
    headers["X-Agent-Tool"] = tool_name
    headers["X-Agent-Permission"] = permission
    request = Request(url, data=body, method=method, headers=headers)
    started = time.monotonic()
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            parsed: object = json.loads(raw) if raw else {}
            if isinstance(parsed, dict) and "code" in parsed:
                try:
                    success = int(parsed.get("code")) in {0, 200}
                except (TypeError, ValueError):
                    success = False
                if not success:
                    return result("BUSINESS_ERROR", httpStatus=response.status,
                                  elapsedMs=round((time.monotonic() - started) * 1000),
                                  responseKeys=sorted(parsed))
                parsed = parsed.get("data")
            return result("OK", httpStatus=response.status,
                          elapsedMs=round((time.monotonic() - started) * 1000),
                          responseKeys=sorted(parsed) if isinstance(parsed, dict) else [],
                          body=parsed)
    except HTTPError as exc:
        return result("HTTP_ERROR", httpStatus=exc.code,
                      elapsedMs=round((time.monotonic() - started) * 1000))
    except (TimeoutError, socket.timeout):
        return result("TIMEOUT", elapsedMs=round((time.monotonic() - started) * 1000))
    except (URLError, OSError) as exc:
        return result("UNAVAILABLE", errorClass=type(exc).__name__)
    except json.JSONDecodeError:
        return result("INVALID_JSON", elapsedMs=round((time.monotonic() - started) * 1000))


def batch_call(base_url: str, method: str, path: str, *,
               payload: dict[str, object] | None = None,
               timeout: float = 10.0) -> dict[str, object]:
    if method == "GET":
        tool_name, permission = "preview_approval_batch_action", "approval:read"
    elif path.endswith("/reconcile"):
        tool_name, permission = "reconcile_approval_batch_action", "approval:write"
    elif path.endswith("/approve"):
        tool_name, permission = "confirm_approval_batch_action", "approval:write"
    elif path.endswith("/execute"):
        tool_name, permission = "confirm_approval_batch_action", "approval:write"
    else:
        tool_name, permission = "preview_approval_batch_action", "approval:read"
    return http_json_call(base_url, method, path, payload=payload,
                          tool_name=tool_name, permission=permission, timeout=timeout)


def start_batch_operation(prefix: str):
    """Create a real Python Operation used by the Java batch preview binding."""
    from src.runtime.operation_runtime import OperationRuntime
    from src.tools.common.events import set_event_context

    run_id = prefix + "-run"
    thread_id = prefix + "-thread"
    message_id = prefix + "-message"
    set_event_context(run_id, thread_id, "1", os.getenv("OA_AGENT_USER_ID", "1"),
                      conversation_id=prefix + "-conversation", message_id=message_id,
                      origin_run_id=run_id)
    runtime = OperationRuntime.start(
        action_id="approval.write.batch",
        capability_id="approval",
        payload={"testPrefix": prefix},
        operation_key=prefix,
        required=True,
    )
    if runtime is None:
        raise RuntimeError("Operation Runtime unavailable")
    if runtime.operation.status == "COLLECTING_INFO":
        runtime.transition("READY", event_type="operation.ready")
    if runtime.operation.status == "READY":
        runtime.transition("RUNNING", event_type="operation.running")
    return runtime, run_id, thread_id, message_id


def finish_batch_operation(runtime, status: str, details: dict[str, object]) -> None:
    try:
        if runtime.operation.status == "RUNNING":
            runtime.transition(status, event_type="operation.test.finished", data=details)
        runtime.patch_result(details, event_type="operation.test.result")
    except Exception:
        pass
    finally:
        runtime.close()


def batch_task_states(base_url: str, task_ids: list[str]) -> list[dict[str, object]]:
    states = []
    for task_id in task_ids:
        observed = batch_call(base_url, "GET", f"/agent/tools/tasks/{task_id}")
        states.append({"taskId": task_id, "status": observed.get("status"),
                       "httpStatus": observed.get("httpStatus")})
    return states


def response_metadata(response: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in response.items() if key != "body"}


def wait_for_java(base_url: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        probe = http_call(base_url, "GET", "/agent/tools/approvals/inbox",
                          params={"pageNo": "1", "pageSize": "1"},
                          tool_name="search_my_pending_approvals", permission="approval:read")
        if probe.get("status") == "OK":
            return True
        time.sleep(0.5)
    return False


def batch_atomicity_fault(args: argparse.Namespace, base_url: str) -> dict[str, object]:
    task_ids = [value.strip() for value in (args.batch_task_ids or "").split(",") if value.strip()]
    mode = str(args.batch_mode or "THROW").upper()
    if not args.live:
        return result("DRY_RUN", mode=mode, wouldVerify=[
            "real Java preview and Approval decision", "failure after first Flowable mutation",
            "all-or-nothing task state", "process interruption and read-only reconciliation",
        ])
    if len(task_ids) < 2 or len(task_ids) > 20:
        return result("BLOCKED", mode=mode, reason="--batch-task-ids requires 2 to 20 existing pending task IDs")
    prefix = "kodagent-batch-fault-" + uuid.uuid4().hex[:12]
    runtime = None
    preview_id = None
    try:
        runtime, run_id, thread_id, message_id = start_batch_operation(prefix)
        operation_id = runtime.operation_id
        preview = batch_call(base_url, "POST", "/agent/tools/approvals/batch/preview", payload={
            "action": "APPROVE",
            "reason": "故障演练，不应提交",
            "taskIds": task_ids,
            "previewMessageId": message_id,
            "runId": run_id,
            "threadId": thread_id,
            "operationId": operation_id,
        })
        body = preview.get("body") if preview.get("status") == "OK" else None
        if not isinstance(body, dict):
            finish_batch_operation(runtime, "FAILED", {"stage": "preview", "status": preview.get("status")})
            return result("FAILED", mode=mode, operationId=operation_id,
                          preview=response_metadata(preview))
        preview_id = str(body.get("previewId") or "")
        token = str(body.get("confirmationToken") or "")
        decision = batch_call(base_url, "POST", f"/agent/tools/approvals/batch/{preview_id}/approve",
                              payload={"idempotencyKey": prefix + "-decision", "reason": "故障演练"})
        execute = batch_call(base_url, "POST", "/agent/tools/approvals/batch/execute", payload={
            "previewId": preview_id,
            "confirmationToken": token,
            "operationId": operation_id,
            "idempotencyKey": prefix + "-execute",
            "confirmationMessageId": prefix + "-confirmation",
        }, timeout=args.batch_execute_timeout)
        reconcile = None
        if mode == "BLOCK":
            if not wait_for_java(base_url, args.batch_reconcile_wait):
                reconcile = result("BLOCKED", reason="Java has not been restored for reconciliation")
            else:
                reconcile = batch_call(base_url, "POST", f"/agent/tools/approvals/batch/{preview_id}/reconcile",
                                       payload={"confirmationToken": token, "operationId": operation_id,
                                                "idempotencyKey": prefix + "-execute"})
        current = batch_call(base_url, "GET", f"/agent/tools/approvals/batch/{preview_id}")
        task_states = batch_task_states(base_url, task_ids)
        current_body = current.get("body") if current.get("status") == "OK" else None
        current_status = current_body.get("status") if isinstance(current_body, dict) else None
        tasks_pending = all(item.get("status") == "OK" for item in task_states)
        if mode == "THROW":
            # The Java facade intentionally returns a CommonResult business
            # error with HTTP 200 for an expected local failpoint. Treat that
            # transport shape the same as an HTTP exception: the acceptance
            # criterion is the durable MySQL/Agent state, not the status code.
            passed = execute.get("status") in {"HTTP_ERROR", "BUSINESS_ERROR"} \
                and current_status == "APPROVED" and tasks_pending
        elif mode == "BLOCK":
            reconcile_body = reconcile.get("body") if isinstance(reconcile, dict) else None
            passed = (execute.get("status") in {"UNAVAILABLE", "TIMEOUT", "HTTP_ERROR"}
                      and isinstance(reconcile_body, dict)
                      and reconcile_body.get("status") == "NOT_COMMITTED"
                      and current_status == "APPROVED" and tasks_pending)
        else:
            passed = False
        details = {
            "mode": mode, "fixturePrefix": prefix, "operationId": operation_id,
            "previewId": preview_id, "taskIds": task_ids,
            "decisionStatus": decision.get("status"), "executeStatus": execute.get("status"),
            "reconcileStatus": reconcile.get("status") if reconcile else None,
            "reconcileState": (reconcile.get("body", {}).get("status")
                                if isinstance(reconcile, dict) and isinstance(reconcile.get("body"), dict) else None),
            "previewStatusAfter": current_status, "taskStatesAfter": task_states,
            "noPartialCommit": tasks_pending,
        }
        finish_batch_operation(runtime, "FAILED" if not passed else "SUCCEEDED", details)
        return result("OK" if passed else "FAILED", **details)
    except Exception as exc:
        if runtime is not None:
            finish_batch_operation(runtime, "FAILED", {"stage": "exception", "errorClass": type(exc).__name__})
        return result("FAILED", mode=mode, fixturePrefix=prefix, previewId=preview_id,
                      errorClass=type(exc).__name__, error=safe_error(exc))


def dependency_probe(name: str, url: str, *, live: bool) -> dict[str, object]:
    parsed = urlparse(url)
    if not live:
        return result("DRY_RUN", targetHost=parsed.hostname or "", targetPort=parsed.port)
    if name == "java":
        probe = http_call(
            url,
            "GET",
            "/agent/tools/approvals/inbox",
            params={"pageNo": "1", "pageSize": "1"},
            tool_name="search_my_pending_approvals",
            permission="approval:read",
        )
        bad_url = f"{parsed.scheme or 'http'}://127.0.0.1:1"
        outage = http_call(
            bad_url,
            "GET",
            "/agent/tools/approvals/inbox",
            params={"pageNo": "1", "pageSize": "1"},
            timeout=0.5,
            tool_name="search_my_pending_approvals",
            permission="approval:read",
        )
    else:
        probe = redis_ping(url)
        bad_url = replace_port(url, 1)
        outage = redis_ping(bad_url)
    restored = (
        http_call(
            url,
            "GET",
            "/agent/tools/approvals/inbox",
            params={"pageNo": "1", "pageSize": "1"},
            tool_name="search_my_pending_approvals",
            permission="approval:read",
        )
        if name == "java"
        else redis_ping(url)
    )
    return result("OK" if probe["status"] == "OK" and outage["status"] in {"UNAVAILABLE", "TIMEOUT"} and restored["status"] == "OK" else "PARTIAL", initial=probe, injectedUnavailable=outage, restored=restored, injection="client-side invalid endpoint; service process was not stopped")


def replace_port(url: str, port: int) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    auth = ""
    if parsed.username:
        auth = parsed.username
        if parsed.password:
            auth += ":" + parsed.password
        auth += "@"
    return f"{parsed.scheme}://{auth}{host}:{port}{parsed.path or ''}"


def redis_ping(url: str) -> dict[str, object]:
    try:
        import redis

        client = redis.Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        return result("OK")
    except Exception as exc:
        return result("UNAVAILABLE", errorClass=type(exc).__name__)


def action_fault(args: argparse.Namespace, base_url: str) -> dict[str, object]:
    fields = {"approvalId": args.approval_id, "operationId": args.operation_id}
    if not args.action_execute:
        return result("SKIPPED", reason="requires --action-execute and an existing approved action")
    if not args.live:
        return result("DRY_RUN", wouldCall=["action-execute", "action-status", "action-reconcile"])
    if not args.approval_id or not args.operation_id:
        return result("BLOCKED", reason="--approval-id and --operation-id are required")
    key = "kodagent-fault-action-" + uuid.uuid4().hex
    execute = http_call(
        base_url,
        "POST",
        "/agent/tools/tasks/action-execute",
        payload={**fields, "idempotencyKey": key},
        timeout=args.action_timeout,
        tool_name="confirm_approval_task_action",
        permission="approval:write",
    )
    status = http_call(
        base_url,
        "GET",
        "/agent/tools/tasks/action-status",
        params=fields,
        timeout=5,
        tool_name="get_approval_task_action_status",
        permission="approval:read",
    )
    reconcile = http_call(
        base_url,
        "POST",
        "/agent/tools/tasks/action-reconcile",
        payload=fields,
        timeout=5,
        tool_name="reconcile_approval_task_action",
        permission="approval:write",
    )
    return result("OK" if execute["status"] in {"OK", "TIMEOUT"} and status["status"] == "OK" and reconcile["status"] == "OK" else "PARTIAL", execute=execute, status=status, reconcile=reconcile, timeoutInjected=True, idempotencyKeyUsed=True)


def outbox_fault(args: argparse.Namespace) -> dict[str, object]:
    if not args.live:
        return result("DRY_RUN", wouldVerify=["temporary prefixed operation/outbox rows", "two concurrent SKIP LOCKED claims", "semantic duplicate rejection", "out-of-order aggregate versions"])
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        return result("BLOCKED", reason="psycopg is not installed")
    dsn = os.getenv("OA_AGENT_RUNTIME_POSTGRES_URI") or os.getenv("LANGGRAPH_POSTGRES_URI")
    if not dsn:
        return result("BLOCKED", reason="runtime PostgreSQL DSN is not configured")
    prefix = "kodagent-fault-" + uuid.uuid4().hex[:12]
    operation_id = prefix + "-operation"
    event_ids = [prefix + "-v2", prefix + "-v1"]
    inserted = False
    try:
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            with conn.transaction():
                conn.execute("INSERT INTO agent_runtime.operation (operation_id, action_id, capability_id, tenant_id, user_id, thread_id, origin_run_id, current_run_id, message_id, status, payload) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'READY', '{}'::jsonb)", (operation_id, "fault.verify", "fault", "fault-tenant", "fault-user", prefix, prefix, prefix, prefix))
                conn.execute("INSERT INTO agent_runtime.outbox (event_id, source, aggregate_type, aggregate_id, aggregate_version, payload) VALUES (%s, 'fault-verify', 'operation', %s, 2, %s), (%s, 'fault-verify', 'operation', %s, 1, %s)", (event_ids[0], operation_id, json.dumps({"event_type": "fault.v2", "test_prefix": prefix}), event_ids[1], operation_id, json.dumps({"event_type": "fault.v1", "test_prefix": prefix})))
                inserted = True
        claims: list[dict[str, object]] = []
        lock = threading.Lock()

        def worker(name: str) -> None:
            with psycopg.connect(dsn, row_factory=dict_row) as conn:
                with conn.transaction():
                    rows = conn.execute("WITH candidates AS (SELECT event_id FROM agent_runtime.outbox WHERE event_id LIKE %s AND published_at IS NULL AND dead_lettered_at IS NULL AND next_attempt_at <= CURRENT_TIMESTAMP AND (lease_until IS NULL OR lease_until <= CURRENT_TIMESTAMP) ORDER BY created_at, event_id FOR UPDATE SKIP LOCKED LIMIT 1) UPDATE agent_runtime.outbox AS o SET attempts=o.attempts+1, lease_owner=%s, lease_until=CURRENT_TIMESTAMP + INTERVAL '30 seconds' FROM candidates WHERE o.event_id=candidates.event_id RETURNING o.event_id, o.aggregate_version, o.lease_owner", (prefix + "%", name)).fetchall()
                    with lock:
                        claims.extend([dict(row) for row in rows])

        threads = [threading.Thread(target=worker, args=(prefix + "-worker-a",)), threading.Thread(target=worker, args=(prefix + "-worker-b",))]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            rows = conn.execute("SELECT event_id, aggregate_version, lease_owner, attempts FROM agent_runtime.outbox WHERE event_id LIKE %s ORDER BY aggregate_version", (prefix + "%",)).fetchall()
            duplicate = conn.execute("INSERT INTO agent_runtime.outbox (event_id, source, aggregate_type, aggregate_id, aggregate_version, payload) VALUES (%s, 'fault-verify', 'operation', %s, 2, %s) ON CONFLICT DO NOTHING RETURNING event_id", (prefix + "-duplicate", operation_id, json.dumps({"event_type": "fault.v2", "test_prefix": prefix}))).fetchone()
            duplicate_rejected = duplicate is None
            conn.execute("DELETE FROM agent_runtime.outbox WHERE event_id LIKE %s", (prefix + "%",))
            conn.execute("DELETE FROM agent_runtime.operation WHERE operation_id = %s", (operation_id,))
        return result("OK" if len(claims) == 2 and len({str(x["lease_owner"]) for x in claims}) >= 1 and duplicate_rejected else "FAILED", fixturePrefix=prefix, inserted=inserted, claimCount=len(claims), claims=[{"worker": x["lease_owner"], "version": x["aggregate_version"]} for x in claims], rowsAfterClaim=[{"version": x["aggregate_version"], "attempts": x["attempts"]} for x in rows], duplicateSemanticEventRejected=duplicate_rejected, outOfOrderVersionsObserved=[x["aggregate_version"] for x in rows])
    except Exception as exc:
        return result("FAILED", fixturePrefix=prefix, errorClass=type(exc).__name__, error=safe_error(exc), fixtureInserted=inserted)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="run dependency probes and temporary PostgreSQL fixture")
    parser.add_argument("--action-execute", action="store_true", help="also issue one real action-execute using supplied existing IDs")
    parser.add_argument("--approval-id")
    parser.add_argument("--operation-id")
    parser.add_argument("--action-timeout", type=float, default=0.01)
    parser.add_argument("--batch-task-ids", help="comma-separated existing pending task IDs for real batch fault acceptance")
    parser.add_argument("--batch-mode", choices=["THROW", "BLOCK"], default="THROW")
    parser.add_argument("--batch-execute-timeout", type=float, default=60.0)
    parser.add_argument("--batch-reconcile-wait", type=float, default=45.0)
    parser.add_argument("--java-url", default=os.getenv("OA_AGENT_BASE_URL", "http://127.0.0.1:48080"))
    parser.add_argument("--redis-url", default=os.getenv("OA_AGENT_REDIS_URL", "redis://127.0.0.1:16379/0"))
    parser.add_argument("--json-out", help="write the metadata-only report to this file")
    args = parser.parse_args()
    report: dict[str, object] = {"script": "verify-agent-faults", "startedAt": now(), "mode": "LIVE" if args.live else "DRY_RUN", "productionCodeChanged": False, "cases": {}}
    report["cases"]["javaClientTimeoutActionStatusReconcile"] = action_fault(args, args.java_url)
    if args.batch_task_ids:
        report["cases"][f"realJavaBatchAtomicity_{args.batch_mode.lower()}"] = batch_atomicity_fault(args, args.java_url)
    report["cases"]["runtimePostgresTwoWorkerOutbox"] = outbox_fault(args)
    report["cases"]["javaUnavailableRestore"] = dependency_probe("java", args.java_url, live=args.live)
    report["cases"]["redisUnavailableRestore"] = dependency_probe("redis", args.redis_url, live=args.live)
    report["finishedAt"] = now()
    encoded = json.dumps(report, ensure_ascii=True, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    failed_statuses = {"PARTIAL", "FAILED", "BLOCKED"}
    return 0 if all(item.get("status") not in failed_statuses for item in report["cases"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
