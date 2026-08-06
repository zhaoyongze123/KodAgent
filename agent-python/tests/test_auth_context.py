from __future__ import annotations

from src.tools.common import auth


def test_java_request_config_does_not_write_request_identity_to_process_environment(monkeypatch):
    """Request identity must stay scoped to the current run, not os.environ."""

    monkeypatch.setattr(
        auth,
        "get_config",
        lambda: {
            "metadata": {
                "identityTicket": "ticket-for-current-run",
                "userId": "42",
                "tenantId": "7",
            }
        },
    )
    monkeypatch.delenv("OA_AGENT_CONTEXT_USER_ID", raising=False)
    monkeypatch.delenv("OA_AGENT_CONTEXT_TENANT_ID", raising=False)
    monkeypatch.setenv("OA_AGENT_API_KEY", "test-agent-key")

    _base_url, headers = auth._java_request_config()

    assert headers["X-Agent-Identity"] == "ticket-for-current-run"
    assert "OA_AGENT_CONTEXT_USER_ID" not in auth.os.environ
    assert "OA_AGENT_CONTEXT_TENANT_ID" not in auth.os.environ


def test_java_request_config_rejects_missing_service_key_outside_console(monkeypatch):
    monkeypatch.delenv("OA_AGENT_API_KEY", raising=False)
    monkeypatch.delenv("OA_AGENT_CONSOLE_DEV_MODE", raising=False)

    try:
        auth._java_request_config()
    except RuntimeError as exc:
        assert "OA_AGENT_API_KEY" in str(exc)
    else:  # pragma: no cover - the assertion documents the security boundary
        raise AssertionError("missing service key must not fall back to a built-in key")
