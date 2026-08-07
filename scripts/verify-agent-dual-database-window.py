#!/usr/bin/env python3
"""Verify recovery when the local OA MySQL and Agent PostgreSQL are both down.

This is a local acceptance harness. It uses one prefixed Agent event as an
audit-only fixture and read-only Java approval endpoints. It never creates an
OA draft, approval task, Flowable process, or business record.
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
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / "agent-python" / ".env")
except Exception:
    pass


CONTAINERS = {
    "postgres": "kodagent-langgraph-postgres",
    "mysql": "ruoyi-mysql",
}
SENSITIVE = re.compile(
    r"(?i)(authorization|x-agent-key|x-agent-identity|api[-_ ]?key|token|secret|password)\s*[:=]\s*[^,; ]+"
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_error(exc: BaseException) -> str:
    value = SENSITIVE.sub(r"\1=<redacted>", str(exc))
    for name in ("OA_AGENT_API_KEY", "OA_AGENT_IDENTITY", "OA_AGENT_IDENTITY_SECRET"):
        secret = os.getenv(name)
        if secret:
            value = value.replace(secret, "<redacted>")
    return value[:240]


def docker(*args: str, timeout: float = 20.0) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            ["docker", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (completed.stdout or completed.stderr or "").strip()
        return completed.returncode == 0, output[:240]
    except Exception as exc:
        return False, safe_error(exc)


def container_running(name: str) -> bool:
    ok, output = docker("inspect", "-f", "{{.State.Running}}", name)
    return ok and output == "true"


def tcp_probe(port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_tcp(port: int, expected: bool, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if tcp_probe(port) == expected:
            return True
        time.sleep(0.5)
    return tcp_probe(port) == expected


def java_headers(tool: str, permission: str) -> dict[str, str]:
    key = os.getenv("OA_AGENT_API_KEY")
    secret = os.getenv("OA_AGENT_IDENTITY_SECRET", "")
    if not key or len(secret) < 32:
        raise RuntimeError("Java Agent credentials are not configured")
    user = os.getenv("OA_AGENT_USER_ID", "1")
    tenant = os.getenv("OA_AGENT_TENANT_ID", "1")
    payload = {
        "userId": int(user) if user.isdigit() else user,
        "tenantId": int(tenant) if tenant.isdigit() else tenant,
        "issuedAt": int(time.time()),
        "expiresAt": int(time.time()) + 120,
        "nonce": str(uuid.uuid4()),
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
    ticket = encoded + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Agent-Key": key,
        "X-Agent-Identity": ticket,
        "X-Agent-Tool": tool,
        "X-Agent-Permission": permission,
    }


def java_call(
    base_url: str,
    method: str,
    path: str,
    *,
    tool: str,
    permission: str,
    payload: dict[str, object] | None = None,
    params: dict[str, object] | None = None,
    timeout: float = 2.0,
) -> tuple[str, object | None, dict[str, object]]:
    url = base_url.rstrip("/") + path
    if params:
        url += "?" + urlencode(params)
    body = json.dumps(payload).encode() if payload is not None else None
    started = time.monotonic()
    try:
        request = Request(
            url,
            data=body,
            method=method,
            headers=java_headers(tool, permission),
        )
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            decoded: object = json.loads(raw) if raw else None
            if isinstance(decoded, dict) and "code" in decoded:
                try:
                    code = int(decoded.get("code"))
                except (TypeError, ValueError):
                    code = -1
                if code not in {0, 200}:
                    return "BUSINESS_ERROR", None, {
                        "httpStatus": response.status,
                        "elapsedMs": round((time.monotonic() - started) * 1000),
                        "responseKeys": sorted(decoded),
                    }
                decoded = decoded.get("data")
            return "OK", decoded, {
                "httpStatus": response.status,
                "elapsedMs": round((time.monotonic() - started) * 1000),
                "responseKeys": sorted(decoded) if isinstance(decoded, dict) else [],
            }
    except HTTPError as exc:
        return "HTTP_ERROR", None, {
            "httpStatus": exc.code,
            "elapsedMs": round((time.monotonic() - started) * 1000),
        }
    except (TimeoutError, socket.timeout):
        return "TIMEOUT", None, {
            "elapsedMs": round((time.monotonic() - started) * 1000),
        }
    except (URLError, OSError) as exc:
        return type(exc).__name__.upper(), None, {
            "elapsedMs": round((time.monotonic() - started) * 1000),
        }
    except json.JSONDecodeError:
        return "INVALID_JSON", None, {
            "elapsedMs": round((time.monotonic() - started) * 1000),
        }


def public_response(status: str, metadata: dict[str, object]) -> dict[str, object]:
    return {"status": status, **metadata}


def retry_java_call(
    operation: Callable[[], tuple[str, object | None, dict[str, object]]],
    accepted: set[str],
    *,
    attempts: int = 8,
    delay: float = 0.75,
) -> tuple[str, object | None, dict[str, object], list[str]]:
    statuses: list[str] = []
    last: tuple[str, object | None, dict[str, object]] = ("UNAVAILABLE", None, {})
    for attempt in range(attempts):
        last = operation()
        statuses.append(last[0])
        if last[0] in accepted:
            return (*last, statuses)
        if attempt + 1 < attempts:
            time.sleep(delay)
    return (*last, statuses)


def event_payload(prefix: str, event_id: str) -> dict[str, object]:
    return {
        "eventId": event_id,
        "runId": prefix + "-run",
        "threadId": prefix + "-thread",
        "messageId": prefix + "-message",
        "type": "run.started",
        "timestamp": now(),
        "data": {"source": "dual-database-window-acceptance"},
    }


def event_call(base_url: str, prefix: str, event_id: str, timeout: float = 2.0):
    return java_call(
        base_url,
        "POST",
        f"/agent/runs/{prefix}-run/events",
        tool="agent_event_persist",
        permission="agent:audit",
        payload=event_payload(prefix, event_id),
        timeout=timeout,
    )


def inbox_call(base_url: str, timeout: float = 2.0):
    return java_call(
        base_url,
        "GET",
        "/agent/tools/approvals/inbox",
        tool="search_my_pending_approvals",
        permission="approval:read",
        params={"pageNo": 1, "pageSize": 1},
        timeout=timeout,
    )


def flowable_call(base_url: str, probe_id: str, timeout: float = 2.0):
    return java_call(
        base_url,
        "GET",
        f"/agent/tools/approvals/applications/{probe_id}",
        tool="get_my_approval_application",
        permission="approval:read",
        timeout=timeout,
    )


def list_events(base_url: str, prefix: str, timeout: float = 5.0):
    return java_call(
        base_url,
        "GET",
        f"/agent/threads/{prefix}-thread/events",
        tool="agent_event_read",
        permission="agent:audit",
        params={"limit": 1000},
        timeout=timeout,
    )


def run(args: argparse.Namespace) -> dict[str, object]:
    base_url = args.java_url
    pg_port = int(args.postgres_port)
    mysql_port = int(args.mysql_port)
    running_before = {key: container_running(name) for key, name in CONTAINERS.items()}
    if not all(running_before.values()):
        return {
            "status": "BLOCKED",
            "reason": "both named database containers must be running before the rehearsal",
            "containersBefore": running_before,
        }

    prefix = "kodagent-dual-db-window-" + uuid.uuid4().hex[:12]
    baseline_event_id = prefix + "-baseline"
    recovered_event_id = prefix + "-recovered"
    flowable_probe_id = prefix + "-no-business-record"
    report: dict[str, object] = {
        "status": "FAILED",
        "mode": "LIVE",
        "fixturePrefix": prefix,
        "containers": CONTAINERS,
        "ports": {"postgres": pg_port, "mysql": mysql_port},
    }
    stopped: list[str] = []
    try:
        baseline_event_status, _, baseline_event_meta = event_call(
            base_url, prefix, baseline_event_id
        )
        baseline_inbox_status, _, baseline_inbox_meta = inbox_call(base_url)
        baseline_flowable_status, _, baseline_flowable_meta = flowable_call(
            base_url, flowable_probe_id
        )
        report["baseline"] = {
            "postgresTcp": tcp_probe(pg_port),
            "mysqlTcp": tcp_probe(mysql_port),
            "eventAppend": public_response(baseline_event_status, baseline_event_meta),
            "approvalInbox": public_response(baseline_inbox_status, baseline_inbox_meta),
            "flowableRead": public_response(baseline_flowable_status, baseline_flowable_meta),
        }
        if baseline_event_status != "OK" or baseline_inbox_status != "OK":
            report["reason"] = "baseline Java probes did not pass"
            return report

        for key in ("postgres", "mysql"):
            ok, output = docker("stop", CONTAINERS[key], timeout=20.0)
            if not ok:
                report["stopError"] = {"container": CONTAINERS[key], "detail": output}
                return report
            stopped.append(key)

        outage_event_status, _, outage_event_meta = event_call(
            base_url, prefix, recovered_event_id, timeout=1.5
        )
        outage_inbox_status, _, outage_inbox_meta = inbox_call(base_url, timeout=1.5)
        outage_flowable_status, _, outage_flowable_meta = flowable_call(
            base_url, flowable_probe_id, timeout=1.5
        )
        report["outage"] = {
            "postgresTcp": tcp_probe(pg_port),
            "mysqlTcp": tcp_probe(mysql_port),
            "eventAppend": public_response(outage_event_status, outage_event_meta),
            "approvalInbox": public_response(outage_inbox_status, outage_inbox_meta),
            "flowableRead": public_response(outage_flowable_status, outage_flowable_meta),
        }
    finally:
        for key in reversed(stopped):
            docker("start", CONTAINERS[key], timeout=30.0)

    restored_tcp = {
        "postgres": wait_for_tcp(pg_port, True),
        "mysql": wait_for_tcp(mysql_port, True),
    }
    recovered_inbox_status, _, recovered_inbox_meta, inbox_attempts = retry_java_call(
        lambda: inbox_call(base_url, timeout=3.0), {"OK"}, delay=0.75
    )
    recovered_flowable_status, _, recovered_flowable_meta, flowable_attempts = retry_java_call(
        lambda: flowable_call(base_url, flowable_probe_id, timeout=3.0),
        {baseline_flowable_status},
        delay=0.75,
    )
    recovered_event_status, recovered_event_body, recovered_event_meta, event_attempts = retry_java_call(
        lambda: event_call(base_url, prefix, recovered_event_id, timeout=3.0),
        {"OK"},
        delay=0.75,
    )
    events_status, events_body, events_meta = list_events(base_url, prefix, timeout=8.0)
    event_ids = []
    if isinstance(events_body, list):
        event_ids = [str(item.get("eventId")) for item in events_body if isinstance(item, dict)]
    report["restored"] = {
        "postgresTcp": restored_tcp["postgres"],
        "mysqlTcp": restored_tcp["mysql"],
        "eventAppend": public_response(recovered_event_status, recovered_event_meta),
        "eventRecoveryAttempts": event_attempts,
        "approvalInbox": public_response(recovered_inbox_status, recovered_inbox_meta),
        "approvalInboxRecoveryAttempts": inbox_attempts,
        "flowableRead": public_response(recovered_flowable_status, recovered_flowable_meta),
        "flowableRecoveryAttempts": flowable_attempts,
        "eventSnapshot": public_response(events_status, events_meta),
        "fixtureEventsRecovered": {
            "status": baseline_event_id in event_ids and recovered_event_id in event_ids,
            "count": len(event_ids),
        },
    }
    expected_failure_statuses = {
        "HTTP_ERROR",
        "TIMEOUT",
        "UNAVAILABLE",
        "URLERROR",
        "OSERROR",
        "CONNECTIONERROR",
    }
    outage_detected = (
        not report["outage"]["postgresTcp"]
        and not report["outage"]["mysqlTcp"]
        and outage_event_status in expected_failure_statuses
        and outage_inbox_status in expected_failure_statuses
        and outage_flowable_status in expected_failure_statuses
    )
    recovered = (
        restored_tcp["postgres"]
        and restored_tcp["mysql"]
        and recovered_event_status == "OK"
        and recovered_inbox_status == "OK"
        and recovered_flowable_status == baseline_flowable_status == "BUSINESS_ERROR"
        and events_status == "OK"
        and baseline_event_id in event_ids
        and recovered_event_id in event_ids
    )
    report["checks"] = {
        "bothDatabasesUnavailable": outage_detected,
        "javaRecoveredAfterRestore": recovered,
        "noBusinessFixtureCreated": True,
    }
    report["status"] = "OK" if outage_detected and recovered else "FAILED"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-url", default=os.getenv("OA_AGENT_BASE_URL", "http://127.0.0.1:48080"))
    parser.add_argument("--postgres-port", default=os.getenv("LANGGRAPH_POSTGRES_PORT", "15432"))
    parser.add_argument("--mysql-port", default=os.getenv("OA_MYSQL_PORT", "13306"))
    parser.add_argument("--json-out", required=True)
    args = parser.parse_args()
    report = {
        "script": "verify-agent-dual-database-window",
        "startedAt": now(),
        "productionCodeChanged": False,
        **run(args),
        "finishedAt": now(),
    }
    output = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
    Path(args.json_out).write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
