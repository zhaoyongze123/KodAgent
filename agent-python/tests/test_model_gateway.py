from __future__ import annotations

import pytest

from src.services import model_runtime


def test_model_config_requires_model_id_but_not_provider_key():
    model_runtime._validate_model_config({"model_id": "240", "model_name": "gpt-5.6-luna"})

    with pytest.raises(model_runtime.ModelRuntimeError, match="模型编号"):
        model_runtime._validate_model_config({"model_name": "gpt-5.6-luna"})


def test_model_build_points_to_java_gateway_and_uses_scoped_identity(monkeypatch):
    monkeypatch.setattr(
        model_runtime,
        "_java_request_config",
        lambda: (
            "http://127.0.0.1:48080",
            {
                "X-Agent-Key": "agent-key",
                "X-Agent-Identity": "identity-ticket",
            },
        ),
    )

    model = model_runtime._build_model(
        {
            "model_id": 240,
            "model_name": "gpt-5.6-luna",
            "provider_name": "claude.aiapis.help",
            "base_url": "https://claude.aiapis.help/v1",
        },
        reasoning_effort="low",
    )

    assert str(model.openai_api_base) == "http://127.0.0.1:48080/agent/internal/models/240"
    assert model.openai_api_key.get_secret_value() == "kodagent-java-model-gateway"
    assert model.default_headers["X-Agent-Key"] == "agent-key"
    assert model.default_headers["X-Agent-Identity"] == "identity-ticket"
    assert model.default_headers["X-Agent-Permission"] == "model:read"
    assert "claude.aiapis.help" not in str(model.openai_api_base)


def test_gateway_url_never_uses_provider_base_url(monkeypatch):
    monkeypatch.setattr(
        model_runtime,
        "_java_request_config",
        lambda: ("http://java.internal/", {"X-Agent-Key": "agent-key"}),
    )

    assert model_runtime._effective_model_base_url(
        {
            "model_id": "240",
            "model_name": "gpt-5.6-luna",
            "base_url": "https://claude.aiapis.help/v1",
        }
    ) == "http://java.internal/agent/internal/models/240"
