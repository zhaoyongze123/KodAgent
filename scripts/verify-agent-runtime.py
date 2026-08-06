#!/usr/bin/env python3
"""Read-only production smoke check for the OA Agent runtime.

The check deliberately verifies the *effective* runtime rather than merely
the configured values: one Java listener, Java-owned action catalog sync,
the model resolved from OA settings, the permission-scoped OA read path, and
optionally one real model request.  Every failure is emitted as JSON and the
process exits non-zero; credentials and provider error bodies are redacted.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent-python"))

try:  # The standalone script should behave like the console deployment.
    from dotenv import load_dotenv

    load_dotenv(ROOT / "agent-python" / ".env")
except Exception:  # pragma: no cover - optional dependency in tiny CI images
    pass

from src.orchestration.action_catalog_sync import (  # noqa: E402
    ActionCatalogSyncError,
    action_catalog_strict,
    action_catalog_sync_enabled,
    sync_action_catalog,
)
from src.services.model_runtime import (  # noqa: E402
    ModelRuntimeError,
    _effective_model_base_url,
    resolve_run_model,
)
from src.tools.common.http_client import java_get, resolve_agent_model  # noqa: E402


def _short_content(value: object) -> str:
    if isinstance(value, list):
        return "".join(
            str(item.get("text", "")) if isinstance(item, dict) else str(item)
            for item in value
        )[:120]
    return str(value)[:120]


def _safe_error(exc: BaseException) -> str:
    """Keep diagnostics useful without ever printing credentials or tokens."""
    text = str(exc)
    for secret_name in ("OA_AGENT_API_KEY", "OA_AGENT_IDENTITY", "OA_AGENT_EMBEDDING_API_KEY"):
        secret = os.getenv(secret_name)
        if secret:
            text = text.replace(secret, "<redacted>")
    text = re.sub(r"(?i)(authorization|api[-_ ]?key|token|secret)\s*[:=]\s*[^,; ]+", r"\1=<redacted>", text)
    return text[:300]


def _local_java_processes() -> list[int]:
    try:
        output = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout
    except Exception:
        return []
    pids: list[int] = []
    for line in output.splitlines():
        if "yudao-server/target/yudao-server.jar" not in line:
            continue
        match = re.match(r"\s*(\d+)\s+", line)
        if match:
            pids.append(int(match.group(1)))
    return pids


def _local_listener(port: int) -> list[int]:
    try:
        output = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout
    except Exception:
        return []
    return [int(value) for value in output.split() if value.isdigit()]


def _java_runtime_check(base_url: str, port: int) -> dict[str, object]:
    host = (urlparse(base_url).hostname or "").lower()
    local_hosts = {"", "localhost", "127.0.0.1", "::1"}
    if host not in local_hosts:
        return {
            "status": "SKIPPED_REMOTE",
            "host": host,
            "singleton": None,
            "listenerMatchesPid": None,
            "reason": "Java Base URL 指向远端，当前机器无法验证远端进程单例",
        }
    pids = _local_java_processes()
    listeners = _local_listener(port)
    singleton = len(pids) == 1
    listener_matches = singleton and listeners == [pids[0]]
    return {
        "status": "OK" if singleton and listener_matches else "FAILED",
        "host": host or "localhost",
        "port": port,
        "processPids": pids,
        "listenerPids": listeners,
        "singleton": singleton,
        "listenerMatchesPid": listener_matches,
    }


def _effective_model_details(model: object, model_config: dict[str, object]) -> dict[str, object]:
    model_name = getattr(model, "model_name", None) or getattr(model, "model", None)
    base_url = (
        getattr(model, "openai_api_base", None)
        or getattr(model, "base_url", None)
        or getattr(getattr(model, "client", None), "base_url", None)
    )
    base_url = str(base_url).rstrip("/") if base_url else ""
    configured_effective = _effective_model_base_url(model_config)
    configured_name = str(model_config.get("model_name") or "")
    return {
        "model": str(model_name or ""),
        "baseUrl": base_url,
        "expectedEffectiveBaseUrl": configured_effective,
        "matchesSettings": bool(
            str(model_name or "") == configured_name
            and base_url.rstrip("/") == configured_effective.rstrip("/")
        ),
        "startupPlaceholder": base_url.startswith("http://127.0.0.1:9"),
        "relayApplied": configured_effective.rstrip("/")
        != str(model_config.get("base_url") or "").rstrip("/"),
    }


def _diagnostic_base_url(configured_base_url: str, java_port: int) -> tuple[str, str | None]:
    """Resolve the Java URL for this diagnostic process only.

    ``host.docker.internal`` is intentionally the production URL inside the
    LangGraph container, but Docker Desktop does not expose that hostname to
    a host-side shell.  When the host-side verifier can prove that the local
    Java listener is present, use localhost for the read-only smoke check and
    report the transport override explicitly.  The runtime itself never uses
    this fallback, so it cannot mask a deployment misconfiguration.
    """
    parsed = urlparse(configured_base_url)
    host = (parsed.hostname or "").lower()
    if host != "host.docker.internal":
        return configured_base_url.rstrip("/"), None
    try:
        socket.getaddrinfo(host, parsed.port or java_port)
        return configured_base_url.rstrip("/"), None
    except OSError:
        if not _local_listener(java_port):
            return configured_base_url.rstrip("/"), None
        scheme = parsed.scheme or "http"
        return f"{scheme}://127.0.0.1:{java_port}", (
            "host.docker.internal 在宿主机不可解析；已使用已确认监听的本机 Java 端口做诊断"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-call", action="store_true", help="发送一次最小真实模型请求")
    parser.add_argument("--java-port", type=int, default=48080)
    parser.add_argument(
        "--allow-offline",
        action="store_true",
        help="允许没有 Java 地址或动作目录同步时以 SKIPPED 结束（仅开发诊断）",
    )
    args = parser.parse_args()

    result: dict[str, object] = {}
    failures: list[str] = []
    configured_base_url = os.getenv("OA_AGENT_BASE_URL", f"http://127.0.0.1:{args.java_port}")
    diagnostic_base_url, transport_note = _diagnostic_base_url(configured_base_url, args.java_port)
    if diagnostic_base_url != configured_base_url.rstrip("/"):
        # This process-local override is deliberately limited to the verifier;
        # business/runtime code keeps the configured URL unchanged.
        os.environ["OA_AGENT_BASE_URL"] = diagnostic_base_url
    result["java"] = _java_runtime_check(configured_base_url, args.java_port)
    if result["java"].get("status") == "FAILED":
        failures.append("JAVA_SINGLETON_OR_LISTENER")

    result["runtimePolicy"] = {
        "actionCatalogSyncEnabled": action_catalog_sync_enabled(),
        "actionCatalogStrict": action_catalog_strict(),
        "configuredBaseUrl": configured_base_url,
        "diagnosticBaseUrl": diagnostic_base_url,
    }
    if transport_note:
        result["runtimePolicy"]["transportNote"] = transport_note
    try:
        sync = sync_action_catalog(run_id=f"runtime-verify-{uuid.uuid4().hex[:12]}", force=True)
        result["catalog"] = {
            "status": sync.status,
            "contractVersion": sync.contract_version,
            "remoteCount": sync.remote_count,
            "fingerprint": sync.fingerprint,
            "drift": list(sync.drift),
        }
        if sync.status != "SYNCED" and not args.allow_offline:
            failures.append("ACTION_CATALOG_NOT_SYNCED")
    except ActionCatalogSyncError as exc:
        result["catalog"] = {"status": "FAILED", "errorCode": exc.code, "error": _safe_error(exc), "details": exc.details}
        failures.append(exc.code)

    model_config: dict[str, object] | None = None
    try:
        model_config = resolve_agent_model(None, "oa-main-agent")
        result["configuredModel"] = {
            "provider": model_config.get("provider_name"),
            "model": model_config.get("model_name"),
            "baseUrl": model_config.get("base_url"),
            "credentialConfigured": bool(model_config.get("apiKey")),
        }
    except Exception as exc:
        result["configuredModel"] = {"status": "FAILED", "error": _safe_error(exc)}
        failures.append("MODEL_SETTINGS_UNAVAILABLE")

    try:
        approvals = java_get("/agent/tools/approvals/inbox", {"pageNo": 1, "pageSize": 1})
        result["oaRead"] = {"status": "OK", "responseKeys": sorted(approvals.keys())}
    except Exception as exc:
        result["oaRead"] = {"status": "FAILED", "error": _safe_error(exc)}
        failures.append("OA_READ_FAILED")

    if args.model_call:
        started = time.monotonic()
        try:
            model = resolve_run_model(None, "auto")
            effective = _effective_model_details(model, model_config or {})
            result["effectiveModel"] = effective
            if not effective["matchesSettings"] or effective["startupPlaceholder"]:
                failures.append("EFFECTIVE_MODEL_MISMATCH")
            response = model.invoke("只回复 OK，不要添加其他内容。")
            result["modelCall"] = {
                "status": "OK",
                "responsePreview": _short_content(getattr(response, "content", response)),
                "elapsedSeconds": round(time.monotonic() - started, 2),
            }
        except ModelRuntimeError as exc:
            result["modelCall"] = {"status": "FAILED", "errorCode": exc.code, "error": _safe_error(exc)}
            failures.append(exc.code)
        except Exception as exc:
            result["modelCall"] = {"status": "FAILED", "error": _safe_error(exc)}
            failures.append("MODEL_CALL_FAILED")

    result["status"] = "OK" if not failures else "FAILED"
    if failures:
        result["failures"] = sorted(set(failures))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
