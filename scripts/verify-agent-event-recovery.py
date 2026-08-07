#!/usr/bin/env python3
"""Verify the Java Run-event Snapshot/Cursor recovery contract.

The test creates only prefixed Agent audit events. It never creates an OA
approval, task, draft, or business mutation. Response bodies and credentials
are kept in-process and the report contains metadata only.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / "agent-python" / ".env")
except Exception:
    pass


SENSITIVE = re.compile(
    r"(?i)(authorization|x-agent-key|x-agent-identity|api[-_ ]?key|token|secret|password)\s*[:=]\s*[^,; ]+"
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_error(exc: BaseException) -> str:
    value = SENSITIVE.sub(r"\1=<redacted>", str(exc))
    for name in ("OA_AGENT_API_KEY", "OA_AGENT_IDENTITY_SECRET"):
        secret = os.getenv(name)
        if secret:
            value = value.replace(secret, "<redacted>")
    return value[:240]


def java_headers(permission: str = "agent:audit") -> dict[str, str]:
    key = os.getenv("OA_AGENT_API_KEY")
    secret = os.getenv("OA_AGENT_IDENTITY_SECRET", "")
    user = os.getenv("OA_AGENT_USER_ID", "1")
    tenant = os.getenv("OA_AGENT_TENANT_ID", "1")
    if not key or len(secret) < 32:
        raise RuntimeError("Java event acceptance requires configured Agent credentials")
    payload = {
        "userId": int(user) if str(user).isdigit() else str(user),
        "tenantId": int(tenant) if str(tenant).isdigit() else str(tenant),
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
        "X-Agent-Tool": "agent_event_persist",
        "X-Agent-Permission": permission,
    }


def call(
    base_url: str,
    method: str,
    path: str,
    *,
    payload: dict[str, object] | None = None,
    params: dict[str, object] | None = None,
    timeout: float = 10,
) -> tuple[str, object | None, dict[str, object]]:
    url = base_url.rstrip("/") + path
    if params:
        url += "?" + urlencode(params)
    body = json.dumps(payload).encode() if payload is not None else None
    started = time.monotonic()
    try:
        request = Request(url, data=body, method=method, headers=java_headers())
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
                    }
                decoded = decoded.get("data")
            return "OK", decoded, {
                "httpStatus": response.status,
                "elapsedMs": round((time.monotonic() - started) * 1000),
            }
    except HTTPError as exc:
        return "HTTP_ERROR", None, {
            "httpStatus": exc.code,
            "elapsedMs": round((time.monotonic() - started) * 1000),
        }
    except (URLError, OSError, TimeoutError) as exc:
        return type(exc).__name__.upper(), None, {
            "elapsedMs": round((time.monotonic() - started) * 1000),
        }
    except json.JSONDecodeError:
        return "INVALID_JSON", None, {
            "elapsedMs": round((time.monotonic() - started) * 1000),
        }


def append_event(
    base_url: str,
    *,
    run_id: str,
    thread_id: str,
    message_id: str,
    event_id: str,
    event_type: str,
    data: dict[str, object] | None = None,
    **fields: object,
) -> tuple[str, object | None, dict[str, object]]:
    event = {
        "eventId": event_id,
        "runId": run_id,
        "threadId": thread_id,
        "messageId": message_id,
        "type": event_type,
        "timestamp": now(),
        "data": data or {},
        **fields,
    }
    return call(base_url, "POST", f"/agent/runs/{run_id}/events", payload=event)


def event_cursor(event: object) -> int | None:
    if not isinstance(event, dict):
        return None
    cursor = event.get("eventCursor")
    if isinstance(cursor, dict):
        value = cursor.get("cursor")
        if isinstance(value, int):
            return value
    value = event.get("sequence")
    return value if isinstance(value, int) else None


def list_events(base_url: str, thread_id: str, after_cursor: int | None = None) -> tuple[str, list[dict[str, object]], dict[str, object]]:
    params: dict[str, object] = {"limit": 1000}
    if after_cursor is not None:
        params["afterCursor"] = after_cursor
    status, body, metadata = call(
        base_url,
        "GET",
        f"/agent/threads/{thread_id}/events",
        params=params,
    )
    if status != "OK" or not isinstance(body, list):
        return status, [], metadata
    return status, [item for item in body if isinstance(item, dict)], metadata


def run(args: argparse.Namespace) -> dict[str, object]:
    if not args.live:
        return {
            "status": "DRY_RUN",
            "cases": {
                "snapshotCursor": "would append and read real Java events",
                "narrationRevision": "would verify Snapshot catches same-cursor upsert",
                "duplicateEvent": "would verify event ID idempotency",
                "durableOrder": "would verify Java cursor order",
            },
        }

    prefix = "kodagent-browser-recovery-" + uuid.uuid4().hex[:12]
    run_id = prefix + "-run"
    thread_id = prefix + "-thread"
    message_id = prefix + "-message"
    narration_id = prefix + "-narration"
    try:
        checks: dict[str, object] = {}
        for event_id, event_type, data in [
            (prefix + "-started", "run.started", {"text": "Agent 开始执行"}),
            (narration_id, "narration.upsert", {}),
            (prefix + "-paused", "run.paused", {"text": "等待用户确认"}),
        ]:
            fields: dict[str, object] = {}
            if event_type == "narration.upsert":
                fields = {
                    "entryId": narration_id,
                    "revision": 1,
                    "status": "streaming",
                    "text": "正在准备审批卡片",
                }
            status, _, metadata = append_event(
                args.java_url,
                run_id=run_id,
                thread_id=thread_id,
                message_id=message_id,
                event_id=event_id,
                event_type=event_type,
                data=data,
                **fields,
            )
            if status != "OK":
                return {"status": "FAILED", "stage": event_type, "response": metadata}

        status, snapshot_before, metadata = list_events(args.java_url, thread_id)
        if status != "OK":
            return {"status": "FAILED", "stage": "snapshot_before", "response": metadata}
        snapshot_cursor = max((event_cursor(item) or 0 for item in snapshot_before), default=0)

        status, _, metadata = append_event(
            args.java_url,
            run_id=run_id,
            thread_id=thread_id,
            message_id=message_id,
            event_id=narration_id,
            event_type="narration.upsert",
            data={},
            entryId=narration_id,
            revision=2,
            status="completed",
            text="审批卡片已恢复",
        )
        if status != "OK":
            return {"status": "FAILED", "stage": "narration_revision", "response": metadata}

        for event_id, event_type, data in [
            (prefix + "-resumed", "run.resumed", {"text": "恢复执行"}),
            (prefix + "-completed", "run.completed", {"text": "执行完成"}),
        ]:
            status, _, metadata = append_event(
                args.java_url,
                run_id=run_id,
                thread_id=thread_id,
                message_id=message_id,
                event_id=event_id,
                event_type=event_type,
                data=data,
            )
            if status != "OK":
                return {"status": "FAILED", "stage": event_type, "response": metadata}

        delta_status, delta, delta_metadata = list_events(
            args.java_url, thread_id, after_cursor=snapshot_cursor
        )
        full_status, snapshot_after, full_metadata = list_events(args.java_url, thread_id)

        duplicate_status, duplicate_body, duplicate_metadata = append_event(
            args.java_url,
            run_id=run_id,
            thread_id=thread_id,
            message_id=message_id,
            event_id=narration_id,
            event_type="narration.upsert",
            data={},
            entryId=narration_id,
            revision=2,
            status="completed",
            text="审批卡片已恢复",
        )

        cursors = [event_cursor(item) for item in snapshot_after]
        valid_cursors = [value for value in cursors if value is not None]
        narration_rows = [
            item for item in snapshot_after if item.get("type") == "narration.upsert"
        ]
        narration = narration_rows[0] if len(narration_rows) == 1 else {}
        event_ids = [str(item.get("eventId")) for item in snapshot_after]
        duplicate_event_ids = len(event_ids) != len(set(event_ids))
        duplicate_created = (
            duplicate_body.get("created")
            if isinstance(duplicate_body, dict)
            else None
        )
        duplicate_cursor = (
            duplicate_body.get("eventCursor")
            if isinstance(duplicate_body, dict)
            else None
        )
        original_cursor = event_cursor(narration)
        checks.update(
            {
                "snapshotBeforeCount": len(snapshot_before),
                "snapshotCursor": snapshot_cursor,
                "deltaStatus": delta_status,
                "deltaTypes": [str(item.get("type")) for item in delta],
                "fullSnapshotCount": len(snapshot_after),
                "narrationRevision": narration.get("revision"),
                "narrationTextRecovered": narration.get("text"),
                "snapshotCatchesSameCursorUpsert": narration.get("revision") == 2,
                "deltaContainsNewRunFacts": {"run.resumed", "run.completed"}.issubset(
                    {str(item.get("type")) for item in delta}
                ),
                "orderedDurableCursors": valid_cursors == sorted(valid_cursors),
                "noDuplicateEventIds": not duplicate_event_ids,
                "duplicateAppendStatus": duplicate_status,
                "duplicateAppendCreated": duplicate_created,
                "duplicateAppendKeepsCursor": (
                    isinstance(duplicate_cursor, dict)
                    and duplicate_cursor.get("cursor") == original_cursor
                ),
            }
        )
        ok = (
            full_status == "OK"
            and delta_status == "OK"
            and checks["snapshotCatchesSameCursorUpsert"]
            and checks["deltaContainsNewRunFacts"]
            and checks["orderedDurableCursors"]
            and checks["noDuplicateEventIds"]
            and duplicate_status == "OK"
            and duplicate_created is False
            and checks["duplicateAppendKeepsCursor"]
        )
        return {
            "status": "OK" if ok else "FAILED",
            "mode": "LIVE",
            "fixturePrefix": prefix,
            "runId": run_id,
            "threadId": thread_id,
            "cases": checks,
            "responseMetadata": {"delta": delta_metadata, "full": full_metadata, "duplicate": duplicate_metadata},
        }
    except Exception as exc:
        return {"status": "FAILED", "fixturePrefix": prefix, "errorClass": type(exc).__name__, "error": safe_error(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--java-url", default=os.getenv("OA_AGENT_BASE_URL", "http://127.0.0.1:48080"))
    parser.add_argument("--json-out")
    args = parser.parse_args()
    report = {"script": "verify-agent-event-recovery", "startedAt": now(), "productionCodeChanged": False, **run(args), "finishedAt": now()}
    encoded = json.dumps(report, ensure_ascii=True, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report.get("status") in {"OK", "DRY_RUN"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
