"""Run-scoped dynamic model selection for DeepAgents."""

from __future__ import annotations

import hashlib
import os
import re
import time
from contextvars import ContextVar
from threading import Lock
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from langgraph.config import get_config

from ..tools.common.events import (
    build_event,
    current_agent_context,
    is_run_paused,
    sync_runtime_event_context,
)
from ..tools.common.auth import _java_request_config
from ..tools.common.http_client import persist_agent_event, resolve_agent_model
from ..orchestration.action_catalog_sync import ActionCatalogSyncError, sync_action_catalog
from .conversation_router import clear_route_reasoning_policy, get_route_reasoning_policy
from .narration_stream import NarrationStreamingModel, stream_model_output_enabled


_MODEL_CONTEXT: ContextVar[tuple[str, str, str, str, ChatOpenAI] | None] = ContextVar(
    "kodagent_model_context", default=None
)
_RUN_STARTED_AT: ContextVar[float | None] = ContextVar(
    "kodagent_run_started_at", default=None
)
_RUN_START_TIMES: dict[str, float] = {}
_RUN_START_TIMES_LOCK = Lock()


class ModelRuntimeError(RuntimeError):
    """Stable provider error contract exposed to the Agent/UI boundary."""

    def __init__(self, code: str, message: str, *, details: Any = None):
        self.code = code
        self.details = details
        super().__init__(message)


def _classify_provider_error(exc: Exception) -> ModelRuntimeError:
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    try:
        status = int(status) if status is not None else None
    except (TypeError, ValueError):
        status = None
    if status is not None and 400 <= status < 500:
        return ModelRuntimeError(
            "MODEL_REQUEST_INVALID",
            "当前配置的模型供应商请求参数无效，请检查模型设置或工具调用格式。",
            details={"statusCode": status},
        )
    return ModelRuntimeError(
        "MODEL_PROVIDER_UNAVAILABLE",
        f"MODEL_PROVIDER_UNAVAILABLE: 当前配置的模型供应商暂时不可用，请稍后重试。 ({str(exc)[:200]})",
        details={"statusCode": status, "exceptionType": type(exc).__name__},
    )


class _SiliconFlowChatOpenAI(ChatOpenAI):
    """Chat Completions client with SiliconFlow's tool-call replay field.

    LangChain intentionally serializes only the standard OpenAI assistant
    fields. SiliconFlow's thinking-enabled tool protocol additionally checks
    for a top-level ``reasoning_content`` field on every assistant message
    that contains tool calls. Putting the value in ``additional_kwargs`` is
    insufficient because the standard converter drops it before the HTTP
    request is sent. Keep this provider-specific workaround at the transport
    boundary so checkpoint messages remain provider-neutral.
    """

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        messages = payload.get("messages") or []
        source_messages = self._convert_input(input_).to_messages()
        for index, message in enumerate(source_messages):
            if not isinstance(message, AIMessage) or not message.tool_calls:
                continue
            if index >= len(messages) or messages[index].get("role") != "assistant":
                continue
            provider_reasoning = (message.additional_kwargs or {}).get(
                "reasoning_content"
            )
            # A single whitespace is deliberate. It satisfies SiliconFlow's
            # required-field validation without fabricating model reasoning.
            messages[index].setdefault(
                "reasoning_content",
                provider_reasoning if provider_reasoning is not None else " ",
            )
        return payload


def _requested_model_id() -> str | None:
    try:
        config = get_config()
    except RuntimeError:
        return None
    configurable = config.get("configurable") or {}
    metadata = config.get("metadata") or {}
    value = (
        configurable.get("modelId")
        or configurable.get("model_id")
        or metadata.get("modelId")
        or metadata.get("model_id")
    )
    return str(value) if value is not None and str(value).strip() else None


def _requested_reasoning_effort() -> str:
    try:
        config = get_config()
    except RuntimeError:
        return "auto"
    configurable = config.get("configurable") or {}
    metadata = config.get("metadata") or {}
    value = configurable.get("reasoningEffort") or metadata.get("reasoningEffort") or "auto"
    value = str(value).lower()
    # Route policy intentionally has only two modes. Keep legacy callers
    # compatible by collapsing any old medium/high request to low.
    if value == "off":
        return "off"
    if value in {"low", "medium", "high"}:
        return "low"
    return "auto"


def _effective_reasoning_effort() -> str:
    """Use the route policy once it exists; retain Run input before routing."""
    route_policy = get_route_reasoning_policy()
    return route_policy.reasoning_effort if route_policy is not None else _requested_reasoning_effort()


def _wrap_runtime_model(model: Any) -> NarrationStreamingModel:
    """Opt child model output into narration without changing root call sites."""
    configured_extra_body = getattr(model, "extra_body", None)
    qwen3_extra_body = (
        configured_extra_body
        if isinstance(configured_extra_body, dict)
        and isinstance(configured_extra_body.get("chat_template_kwargs"), dict)
        else None
    )
    wrapper_options: dict[str, Any] = {}
    if stream_model_output_enabled():
        wrapper_options["stream_model_output"] = True
    # Keep the wrapper's generic constructor path provider-neutral.  The
    # provider-specific body is passed only for Qwen3 models.
    if qwen3_extra_body is not None:
        wrapper_options["qwen3_extra_body"] = qwen3_extra_body
    return NarrationStreamingModel(model, **wrapper_options)


def _is_siliconflow(model_config: dict[str, Any]) -> bool:
    """Detect SiliconFlow only from the effective Java-bound configuration."""
    provider = str(model_config.get("provider_name") or "")
    base_url = str(model_config.get("base_url") or "")
    return "siliconflow" in f"{provider} {base_url}".lower()


def _is_qwen3(model_config: dict[str, Any]) -> bool:
    """Detect Qwen3 chat endpoints that use vLLM chat-template controls."""
    provider = str(model_config.get("provider_name") or "")
    model_name = str(model_config.get("model_name") or "")
    # Accept the common spellings ``Qwen3`` and ``Qwen-3`` without making the
    # rule depend on a particular provider name.  This is deliberately a
    # model-only capability check; all other models retain the OpenAI-compatible
    # defaults selected by the route.
    normalized = re.sub(r"[^a-z0-9]", "", f"{provider} {model_name}".lower())
    return "qwen3" in normalized


def _model_config_fingerprint(model_config: dict[str, Any]) -> str:
    """Identify the effective model without ever depending on a provider key."""
    values = "\x1f".join(
        (
            str(model_config.get("model_id") or "").strip(),
            str(model_config.get("provider_name") or "").strip(),
            str(model_config.get("model_name") or "").strip(),
            str(model_config.get("base_url") or "").strip().rstrip("/"),
        )
    )
    return hashlib.sha256(values.encode("utf-8")).hexdigest()


def _validate_model_config(model_config: dict[str, Any]) -> None:
    required = (
        ("model_id", "设置中缺少模型编号。"),
        ("model_name", "设置中缺少模型名称。"),
    )
    for field, message in required:
        if not str(model_config.get(field) or "").strip():
            raise ModelRuntimeError("MODEL_CONFIG_INVALID", message)


def _effective_model_base_url(model_config: dict[str, Any]) -> str:
    """Point the LangChain client at Java's credential-holding gateway."""
    return _model_gateway_config(model_config)[0]


def _model_gateway_config(model_config: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """Resolve the Java gateway URL and scoped headers once per model build."""
    base_url, headers = _java_request_config()
    model_id = str(model_config.get("model_id") or "").strip()
    if not model_id:
        raise ModelRuntimeError("MODEL_CONFIG_INVALID", "设置中缺少模型编号。")
    return (
        f"{base_url.rstrip('/')}/agent/internal/models/{model_id}",
        {
            **headers,
            "X-Agent-Tool": "agent_model_chat_completion",
            "X-Agent-Permission": "model:read",
        },
    )


def _model_gateway_headers(model_config: dict[str, Any]) -> dict[str, str]:
    """Build per-Run Java headers without exposing provider credentials."""
    return _model_gateway_config(model_config)[1]


def _build_model(model_config: dict[str, Any], reasoning_effort: str = "auto") -> ChatOpenAI:
    _validate_model_config(model_config)
    siliconflow = _is_siliconflow(model_config)
    qwen3 = _is_qwen3(model_config)
    base_url, gateway_headers = _model_gateway_config(model_config)
    options: dict[str, Any] = {
        "model": str(model_config["model_name"]),
        # ChatOpenAI requires a non-empty token even though Java authenticates
        # the request with X-Agent-Key and X-Agent-Identity. This is a local
        # gateway marker, never a provider credential.
        "api_key": "kodagent-java-model-gateway",
        "base_url": base_url,
        "default_headers": {
            **gateway_headers,
            "User-Agent": "kodagent-deepagents/0.1",
        },
        # SiliconFlow and most OpenAI-compatible providers expose Chat
        # Completions, while Responses support is not universal.
        "use_responses_api": False,
        # NarrationStreamingModel consumes the provider's chunks to emit
        # report_progress updates, so the underlying ChatOpenAI must stream.
        "streaming": True,
        # Keep provider retries bounded.  A provider 4xx is never retried by
        # the OpenAI client, while transient 5xx/network failures get only a
        # short, finite retry window and never switch providers.
        "max_retries": min(2, max(0, int(os.getenv("OA_AGENT_MODEL_MAX_RETRIES", "2")))),
        "timeout": 120,
    }
    # Qwen3's vLLM chat template requires its thinking switch in the nested
    # ``chat_template_kwargs`` object.  Keep this branch first so a Qwen3
    # model hosted by SiliconFlow still receives the Qwen3-specific payload.
    if qwen3:
        options["extra_body"] = {
            "chat_template_kwargs": {
                "enable_thinking": False,
            }
        }
    elif reasoning_effort != "auto" and reasoning_effort != "off":
        # All non-Qwen models keep the existing OpenAI-compatible route-level
        # reasoning option. No Qwen/vLLM chat-template body is sent to them.
        options["reasoning_effort"] = reasoning_effort
    model_cls = _SiliconFlowChatOpenAI if siliconflow else ChatOpenAI
    return model_cls(
        **options,
    )


def resolve_run_model(model_id: str | None, reasoning_effort: str = "auto") -> ChatOpenAI:
    run_id = str(current_agent_context().get("runId") or "local-run")
    requested_model_id = str(model_id or "__default__")
    cached = _MODEL_CONTEXT.get()
    # Java settings are the fact source at Run start. Keep that resolved
    # configuration stable for the rest of the Run, but never share it with a
    # later Run: its distinct run id forces a fresh Java resolution.
    if (
        cached
        and cached[0] == run_id
        and cached[1] == requested_model_id
        and cached[2] == reasoning_effort
    ):
        return cached[4]

    try:
        sync_action_catalog(run_id=run_id)
    except ActionCatalogSyncError as exc:
        raise ModelRuntimeError(exc.code, str(exc), details=exc.details) from exc

    model_config = resolve_agent_model(model_id, "oa-main-agent")
    _validate_model_config(model_config)
    fingerprint = _model_config_fingerprint(model_config)
    model = _build_model(model_config, reasoning_effort)
    _MODEL_CONTEXT.set(
        (run_id, requested_model_id, reasoning_effort, fingerprint, model)
    )
    return model


class DynamicModelMiddleware(AgentMiddleware):
    """Replace the startup model with the model selected for this Run."""

    name = "DynamicModelMiddleware"

    def wrap_model_call(self, request, handler):
        model_id = _requested_model_id()
        reasoning_effort = _effective_reasoning_effort()
        # Model resolution errors and provider errors must remain visible to
        # the caller.  Falling back to the startup model could silently switch
        # away from the model selected in OA settings and hide the real cause.
        try:
            return handler(request.override(
                model=_wrap_runtime_model(resolve_run_model(model_id, reasoning_effort))
            ))
        except ModelRuntimeError:
            raise
        except RuntimeError as exc:
            if str(exc).startswith("MODEL_"):
                raise ModelRuntimeError("MODEL_CONFIG_INVALID", str(exc)) from exc
            raise _classify_provider_error(exc) from exc
        except Exception as exc:
            raise _classify_provider_error(exc) from exc

    async def awrap_model_call(self, request, handler):
        model_id = _requested_model_id()
        reasoning_effort = _effective_reasoning_effort()
        try:
            return await handler(request.override(
                model=_wrap_runtime_model(resolve_run_model(model_id, reasoning_effort))
            ))
        except ModelRuntimeError:
            raise
        except RuntimeError as exc:
            if str(exc).startswith("MODEL_"):
                raise ModelRuntimeError("MODEL_CONFIG_INVALID", str(exc)) from exc
            raise _classify_provider_error(exc) from exc
        except Exception as exc:
            raise _classify_provider_error(exc) from exc


class RunLifecycleMiddleware(AgentMiddleware):
    """Persist the final assistant message and terminal Run event server-side.

    The browser still sends a completion event as a retryable UX fallback, but
    durable auditing must not depend on a tab remaining open until the stream
    finishes. This middleware runs inside the main Agent graph and therefore
    also covers API clients and background LangGraph runs.
    """

    name = "RunLifecycleMiddleware"

    def before_agent(self, state, runtime):
        sync_runtime_event_context()
        clear_route_reasoning_policy()
        started = time.perf_counter()
        _RUN_STARTED_AT.set(started)
        run_id = current_agent_context()["runId"]
        if run_id and run_id != "local-run":
            with _RUN_START_TIMES_LOCK:
                _RUN_START_TIMES.setdefault(run_id, started)
        return None

    async def abefore_agent(self, state, runtime):
        return self.before_agent(state, runtime)

    def after_agent(self, state, runtime):
        self._persist_completion(state)
        if not is_run_paused():
            clear_route_reasoning_policy()
        return None

    async def aafter_agent(self, state, runtime):
        return self.after_agent(state, runtime)

    @staticmethod
    def _persist_completion(state) -> None:
        try:
            sync_runtime_event_context()
            context = current_agent_context()
            run_id = context["runId"]
            if not run_id or run_id == "local-run":
                return
            # ``interrupt()`` may unwind through the Agent middleware in some
            # LangGraph versions. In that case after_agent is still invoked,
            # but the Run is paused, not completed. The confirmation Tool sets
            # this context signal before raising the interrupt. Do not consume
            # the start timestamp or write message.completed/run.completed.
            if is_run_paused():
                return
            with _RUN_START_TIMES_LOCK:
                elapsed = _RUN_START_TIMES.pop(run_id, None)
            elapsed = elapsed or _RUN_STARTED_AT.get()
            duration_ms = max(1, int((time.perf_counter() - elapsed) * 1000)) if elapsed else 0

            messages = state.get("messages", []) if isinstance(state, dict) else []
            final_text = ""
            for message in reversed(messages):
                if getattr(message, "type", "") != "ai":
                    continue
                content = getattr(message, "content", "")
                if isinstance(content, str) and content.strip():
                    final_text = content
                    break
                if isinstance(content, list):
                    final_text = "".join(
                        str(item.get("text", "")) for item in content
                        if isinstance(item, dict) and item.get("text")
                    ).strip()
                    if final_text:
                        break

            if final_text:
                message_event = build_event(
                    "message.completed",
                    {"content": final_text, "source": "agent-lifecycle"},
                    final_text,
                )
                message_event["eventId"] = f"{run_id}:message.completed"
                persist_agent_event(message_event)

            completed = build_event(
                "run.completed",
                {"source": "agent-lifecycle"},
                "Agent 执行完成",
            )
            completed["eventId"] = f"{run_id}:completed"
            completed["durationMs"] = duration_ms
            persist_agent_event(completed)
        except Exception:
            # Business output must not fail because audit delivery is being
            # retried by the HTTP client/Outbox.
            return
