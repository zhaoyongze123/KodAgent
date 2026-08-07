from __future__ import annotations

from types import SimpleNamespace

from src import auth as auth_context
from src.tools.common import auth


def test_java_request_config_issues_ticket_from_trusted_run_identity(monkeypatch):
    """Run metadata identifies the tenant; it never supplies the Java ticket."""

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

    monkeypatch.setenv("OA_AGENT_IDENTITY_SECRET", "s" * 32)
    monkeypatch.setattr(auth, "_issue_internal_ticket", lambda user, tenant: f"issued:{user}:{tenant}")

    _base_url, headers = auth._java_request_config()

    assert headers["X-Agent-Identity"] == "issued:42:7"
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


def test_stamp_metadata_normalizes_none_without_dropping_existing_metadata():
    class IdentityUser(dict):
        identity = "tenant:user"

    value = {"metadata": {"caller": "keep", "identityTicket": "caller-ticket", "identity_ticket": "also-ticket"}}
    ctx = SimpleNamespace(
        user=IdentityUser(userId="user", tenantId="tenant", identityTicket="ticket")
    )

    assert auth_context._stamp_metadata(ctx, value) is True
    assert value["metadata"] == {
        "caller": "keep",
        "userId": "user",
        "tenantId": "tenant",
        "owner": "tenant:user",
    }


def test_authenticate_does_not_return_identity_ticket(monkeypatch):
    monkeypatch.setattr(auth_context, "_verify_ticket", lambda ticket: {"userId": "1", "tenantId": "2"})
    result = __import__("asyncio").run(auth_context.authenticate({b"x-agent-identity": b"ticket"}))
    assert "identityTicket" not in result
