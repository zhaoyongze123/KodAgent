from contextvars import ContextVar
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Annotated, Any
from uuid import uuid4

from langchain.tools import InjectedToolCallId, tool
from langgraph.config import get_config, get_stream_writer

from .contracts import ToolResponse, tool_success
from .narration_state import current_revision, next_revision
from .presentation import normalize_presentation
from .run_state import claim_plan, clear_paused, is_paused, mark_paused
from src.services.narration import NarrationPublisher


_RUN_ID: ContextVar[str] = ContextVar("oa_agent_run_id", default="local-run")
_ORIGIN_RUN_ID: ContextVar[str] = ContextVar("oa_agent_origin_run_id", default="")
_RESUME_RUN_ID: ContextVar[str] = ContextVar("oa_agent_resume_run_id", default="")
_THREAD_ID: ContextVar[str] = ContextVar("oa_agent_thread_id", default="local-thread")
_SEQUENCE_HINT: ContextVar[int] = ContextVar("oa_agent_event_sequence_hint", default=0)
_ACTIVE_TOOL_CALL_ID: ContextVar[str] = ContextVar("oa_agent_active_tool_call_id", default="")
_TENANT_ID: ContextVar[str] = ContextVar("oa_agent_tenant_id", default="1")
_USER_ID: ContextVar[str] = ContextVar("oa_agent_user_id", default="1")
_CONVERSATION_ID: ContextVar[str] = ContextVar("oa_agent_conversation_id", default="local-conversation")
_MESSAGE_ID: ContextVar[str] = ContextVar("oa_agent_message_id", default="")
_TASK_ID: ContextVar[str] = ContextVar("oa_agent_task_id", default="")
_OPERATION_ID: ContextVar[str] = ContextVar("oa_agent_operation_id", default="")
_SOURCE_SCOPE: ContextVar[str] = ContextVar("oa_agent_event_source_scope", default="main")
_SOURCE_NAMESPACE: ContextVar[tuple[str, ...]] = ContextVar(
    "oa_agent_event_source_namespace", default=()
)
_EXPLICIT_CONTEXT_BOUND: ContextVar[bool] = ContextVar(
    "oa_agent_explicit_context_bound", default=False
)
_RUN_STARTED_EMITTED: ContextVar[bool] = ContextVar("oa_agent_run_started_emitted", default=False)
_RUN_PAUSED: ContextVar[bool] = ContextVar("oa_agent_run_paused", default=False)
_RUN_PAUSED_RUN_ID: ContextVar[str] = ContextVar("oa_agent_run_paused_run_id", default="")

# A model generally emits one or a few characters per chunk.  Keeping the
# first update immediate and then coalescing the rest gives the user genuine
# streaming feedback without turning a short plan into dozens of PostgreSQL
# writes.  The final Tool execution is always persisted, regardless of this
# throttle.
_NARRATION_STREAM_MIN_INTERVAL_SECONDS = 0.075
_NARRATION_STREAM_MIN_NEW_CHARACTERS = 4


EVENT_ICONS = {
    "route.selected": "🧭",
    "plan.created": "🧠",
    "subagent.started": "🧩",
    "subagent.completed": "✅",
    "tool.started": "🔧",
    "tool.completed": "✅",
    "tool.failed": "❌",
    "draft.created": "📝",
    "approval.approved": "✅",
    "approval.rejected": "❌",
    "run.paused": "⏸️",
    "run.resumed": "▶️",
    "run.completed": "✅",
    "run.failed": "❌",
    "run.cancelled": "🚫",
    "progress": "🧩",
    "workflow.started": "▶️",
    "workflow.node.started": "🔄",
    "workflow.node.completed": "✅",
    "workflow.blocked": "⏸️",
    "workflow.failed": "❌",
    "workflow.completed": "✅",
}


def plain_event_text(text: str) -> str:
    """移除 Tool 自己携带的旧版前缀 Emoji，事件本身不依赖展示层。"""
    return re.sub(r"^(?:[\U0001F300-\U0001FAFF]|[\u2600-\u27BF]|️|\s)+", "", text).strip()


def format_event_text(event: dict[str, Any]) -> str:
    event_type = event.get("type", "")
    data = event.get("data") or {}
    icon = EVENT_ICONS.get(event_type, "")
    if event_type == "tool.completed" and data.get("success") is False:
        icon = "⚠️"
    text = plain_event_text(str(data.get("text", "")))
    return f"{icon} {text}".strip()


def set_event_context(run_id: str, thread_id: str, tenant_id: str = "1", user_id: str = "1",
                      conversation_id: str = "local-conversation", message_id: str = "",
                      origin_run_id: str | None = None, resume_run_id: str | None = None,
                      operation_id: str | None = None) -> None:
    """为一次 Agent 运行设置事件信封上下文。"""
    _RUN_ID.set(run_id)
    _ORIGIN_RUN_ID.set(str(origin_run_id or run_id))
    _RESUME_RUN_ID.set(str(resume_run_id or ""))
    _THREAD_ID.set(thread_id)
    _SEQUENCE_HINT.set(0)
    _ACTIVE_TOOL_CALL_ID.set("")
    _TENANT_ID.set(tenant_id)
    _USER_ID.set(user_id)
    _CONVERSATION_ID.set(conversation_id)
    _MESSAGE_ID.set(message_id)
    _TASK_ID.set("")
    _OPERATION_ID.set(str(operation_id or ""))
    # A console/Gateway context starts at the root graph.  Runtime sync below
    # replaces this with the current checkpoint namespace for subgraphs.
    _SOURCE_SCOPE.set("main")
    _SOURCE_NAMESPACE.set(())
    _RUN_STARTED_EMITTED.set(False)
    _RUN_PAUSED.set(False)
    _RUN_PAUSED_RUN_ID.set("")


def _normalize_checkpoint_namespace(value: Any) -> tuple[str, ...]:
    """Normalize LangGraph's checkpoint namespace without changing its IDs.

    LangGraph stores the namespace path as ``segment|segment`` in
    ``configurable.checkpoint_ns``.  Each segment itself is an opaque value
    such as ``tools:<task-id>`` and must remain intact for SDK correlation.
    """
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        if not text or text in {"__root__", "root", "main"}:
            return ()
        if text.startswith("["):
            try:
                return _normalize_checkpoint_namespace(json.loads(text))
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        values: Sequence[Any] = text.split("|")
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        values = value
    else:
        return ()

    normalized: list[str] = []
    for part in values:
        text = str(part).strip()
        if not text:
            continue
        # A list is normally already segmented, but accepting a nested string
        # keeps fixtures and older runtimes equivalent to RunnableConfig.
        normalized.extend(segment.strip() for segment in text.split("|") if segment.strip())
    return tuple(normalized)


def canonical_source_identity(config: Mapping[str, Any] | None = None) -> tuple[str, tuple[str, ...]]:
    """Return the durable source identity for the current graph execution.

    ``ExecutionInfo.checkpoint_ns`` is the runtime's typed representation;
    ``configurable.checkpoint_ns`` is its RunnableConfig representation.  The
    latter is retained as a fallback for older runtimes and direct tests.
    Missing namespace means the root graph, never an inferred subgraph.
    """
    if not config:
        return "main", ()

    configurable = config.get("configurable") or {}
    runtime = configurable.get("__pregel_runtime")
    execution_info = getattr(runtime, "execution_info", None)
    candidates = (
        getattr(execution_info, "checkpoint_ns", None),
        configurable.get("checkpoint_ns"),
        configurable.get("langgraph_checkpoint_ns"),
        configurable.get("namespace"),
        (config.get("metadata") or {}).get("checkpoint_ns"),
        (config.get("metadata") or {}).get("langgraph_checkpoint_ns"),
        (config.get("metadata") or {}).get("namespace"),
        config.get("checkpoint_ns"),
        config.get("namespace"),
    )
    for candidate in candidates:
        namespace = _normalize_checkpoint_namespace(candidate)
        if namespace:
            return "subgraph", namespace
    return "main", ()


def sync_runtime_event_context() -> None:
    """从 LangGraph 当前 RunnableConfig 注入真实 Thread/Run 上下文。

    控制台会主动设置上下文，但 LangGraph Server 的 Tool 是在服务端线程中
    执行的，不能依赖控制台的 ContextVar。若不在这里同步，事件会落到
    ``local-thread/local-run``，前端按真实 thread 刷新时就无法恢复。
    """
    # Deterministic workflows bind the trusted request envelope explicitly
    # while crossing a nested graph/thread boundary.  Do not let a child
    # RunnableConfig replace that envelope with its own partial metadata.
    if _EXPLICIT_CONTEXT_BOUND.get():
        return
    try:
        config = get_config()
    except Exception:
        return

    configurable = config.get("configurable") or {}
    metadata = config.get("metadata") or {}
    # LangGraph assigns a child span id to ``config.run_id`` while retaining
    # the request's root run id in metadata. Business drafts and HITL proofs
    # are bound to that root id, so prefer metadata for cross-node identity.
    run_id = metadata.get("runId") or metadata.get("run_id") or config.get("run_id")
    origin_run_id = metadata.get("originRunId") or metadata.get("origin_run_id") or metadata.get("runId") or metadata.get("run_id")
    resume_run_id = metadata.get("resumeRunId") or metadata.get("resume_run_id")
    thread_id = configurable.get("thread_id") or metadata.get("threadId") or metadata.get("thread_id")
    tenant_id = metadata.get("tenantId") or metadata.get("tenant_id") or _TENANT_ID.get()
    user_id = metadata.get("userId") or metadata.get("user_id") or _USER_ID.get()
    conversation_id = metadata.get("conversationId") or metadata.get("conversation_id") or _CONVERSATION_ID.get()
    message_id = metadata.get("messageId") or metadata.get("message_id") or _MESSAGE_ID.get()
    task_id = metadata.get("taskId") or metadata.get("task_id") or _TASK_ID.get()
    operation_id = metadata.get("operationId") or metadata.get("operation_id") or _OPERATION_ID.get()
    source_scope, source_namespace = canonical_source_identity(config)
    _SOURCE_SCOPE.set(source_scope)
    _SOURCE_NAMESPACE.set(source_namespace)

    if run_id or thread_id:
        # 不调用 set_event_context：它是一次新 Run 的初始化，会重置 sequence。
        # 这里仅同步当前执行上下文，避免每个 Tool 事件都从 sequence=0 开始。
        _RUN_ID.set(str(run_id or _RUN_ID.get()))
        # A normal run has itself as its origin.  A Gateway/Server resume may
        # explicitly carry both IDs.  The meeting approval boundary also
        # validates these values against its durable interrupt marker, so
        # metadata alone can never authorize a resume.
        _ORIGIN_RUN_ID.set(str(origin_run_id or _ORIGIN_RUN_ID.get() or run_id or ""))
        _RESUME_RUN_ID.set(str(resume_run_id or (run_id if origin_run_id and str(run_id) != str(origin_run_id) else _RESUME_RUN_ID.get()) or ""))
        _THREAD_ID.set(str(thread_id or _THREAD_ID.get()))
        _TENANT_ID.set(str(tenant_id))
        _USER_ID.set(str(user_id))
        _CONVERSATION_ID.set(str(conversation_id))
        _MESSAGE_ID.set(str(message_id))
        _TASK_ID.set(str(task_id or ""))
        _OPERATION_ID.set(str(operation_id or ""))


def current_agent_context() -> dict[str, str]:
    """返回当前 Run 的身份和 Thread 上下文，供需要绑定状态的 Tool 使用。"""
    sync_runtime_event_context()
    return {
        "runId": _RUN_ID.get(),
        "originRunId": _ORIGIN_RUN_ID.get() or _RUN_ID.get(),
        "resumeRunId": _RESUME_RUN_ID.get(),
        "threadId": _THREAD_ID.get(),
        "tenantId": _TENANT_ID.get(),
        "userId": str(_USER_ID.get()),
        "conversationId": _CONVERSATION_ID.get(),
        "messageId": _MESSAGE_ID.get(),
        "taskId": _TASK_ID.get(),
        "operationId": _OPERATION_ID.get(),
    }


@contextmanager
def bind_agent_context(context: Mapping[str, Any]):
    """Bind a trusted request envelope for a nested deterministic workflow.

    LangGraph may execute a child graph in a different context where only a
    partial ``RunnableConfig`` is available.  Workflow state carries this
    envelope explicitly; this scope makes it available to Java-facing tools
    without exposing identity fields in a model tool schema.
    """
    values = {
        _RUN_ID: str(context.get("runId") or ""),
        _ORIGIN_RUN_ID: str(context.get("originRunId") or context.get("runId") or ""),
        _RESUME_RUN_ID: str(context.get("resumeRunId") or ""),
        _THREAD_ID: str(context.get("threadId") or ""),
        _TENANT_ID: str(context.get("tenantId") or ""),
        _USER_ID: str(context.get("userId") or ""),
        _CONVERSATION_ID: str(context.get("conversationId") or ""),
        _MESSAGE_ID: str(context.get("messageId") or ""),
        _TASK_ID: str(context.get("taskId") or ""),
        _OPERATION_ID: str(context.get("operationId") or ""),
    }
    tokens = [variable.set(value) for variable, value in values.items()]
    explicit_token = _EXPLICIT_CONTEXT_BOUND.set(True)
    try:
        yield
    finally:
        _EXPLICIT_CONTEXT_BOUND.reset(explicit_token)
        for variable, token in zip(values, tokens):
            variable.reset(token)


def turn_id_from_context(context: dict[str, Any] | None = None) -> str:
    """Return the stable identity of the current user turn.

    ``messageId`` is supplied by the Gateway in production, but older
    LangGraph Server requests may only carry a run id.  The parent ``task``
    guard and the meeting task memory must use the same fallback; otherwise a
    valid same-run replan is mistaken for an unrelated/unknown turn and gets
    blocked.
    """
    value = context or current_agent_context()
    message_id = str(value.get("messageId") or "").strip()
    if message_id:
        return message_id
    return f"run:{str(value.get('runId') or 'local-run').strip()}"


def set_task_context(task_id: str | None) -> None:
    """Bind subsequent events and writes to the active business task."""
    _TASK_ID.set(str(task_id or ""))


def set_operation_context(operation_id: str | None) -> None:
    """Bind the durable Operation identity for the current workflow scope."""
    _OPERATION_ID.set(str(operation_id or ""))


def set_message_context(message_id: str | None) -> None:
    """Bind the stable user-turn ID when the Gateway omitted metadata."""
    value = str(message_id or "").strip()
    if value:
        _MESSAGE_ID.set(value)


def mark_run_paused() -> None:
    """标记当前 Run 正在等待人工决定。

    该标记和 ``run.paused`` 事件一起设置，供生命周期中间件区分
    ``interrupt`` 的暂停和真正的 Agent 完成。ContextVar 只作为当前执行
    上下文的瞬时信号，可靠恢复仍由 LangGraph Checkpoint 负责。
    """
    _RUN_PAUSED.set(True)
    _RUN_PAUSED_RUN_ID.set(_RUN_ID.get())
    mark_paused(_RUN_ID.get(), scope=f"{_TENANT_ID.get()}:{_THREAD_ID.get()}")


def mark_run_resumed() -> None:
    """清除当前 Run 的暂停标记。"""
    _RUN_PAUSED.set(False)
    _RUN_PAUSED_RUN_ID.set("")
    clear_paused(_RUN_ID.get(), scope=f"{_TENANT_ID.get()}:{_THREAD_ID.get()}")


def is_run_paused() -> bool:
    run_id = _RUN_ID.get()
    process_paused = is_paused(run_id, scope=f"{_TENANT_ID.get()}:{_THREAD_ID.get()}")
    return process_paused or (_RUN_PAUSED.get() and _RUN_PAUSED_RUN_ID.get() == run_id)


def progress_event_type(stage: str) -> tuple[str, str]:
    """Allow exactly one plan heading per Run.

    Main and sub-agent report tools share the same Run.  A later ``stage=plan``
    is still useful progress, but must not create another plan heading in the
    UI or in the audit stream.
    """
    if stage != "plan":
        return "progress", stage
    run_id = _RUN_ID.get()
    scope = f"{_TENANT_ID.get()}:{_THREAD_ID.get()}"
    return ("plan.created", "plan") if claim_plan(run_id, scope=scope) else ("progress", "progress")


def bind_tool_call_id(tool_call_id: str | None) -> str:
    """绑定本次 Tool 调用的稳定 ID，供 started/completed/failed 共用。"""
    if tool_call_id:
        value = str(tool_call_id)
        _ACTIVE_TOOL_CALL_ID.set(value)
        return value
    # Every Tool entry point calls this, including when LangGraph did not
    # inject an ID (for example direct tests or an older runtime). Clearing
    # here prevents the next Tool in the same worker context from inheriting
    # the previous Tool's ID. The first event for the new Tool then creates a
    # local fallback ID and keeps it for that Tool's lifecycle.
    _ACTIVE_TOOL_CALL_ID.set("")
    return ""


def _canonical_event_id(event_type: str, tool_call_id: str | None) -> str | None:
    """Return the retry-stable identity for a tool-scoped event.

    ``emit`` is both the live writer and the persistence producer.  A retry or
    a middleware re-entry must therefore address the same logical phase in
    both paths; a fresh UUID would turn one lifecycle phase into two durable
    rows.  Tool call IDs can be reused by parallel subgraphs, so the source
    scope and namespace are part of the identity as well.
    """
    if not tool_call_id:
        return None
    identity = json.dumps(
        {
            "scope": _SOURCE_SCOPE.get(),
            "namespace": list(_SOURCE_NAMESPACE.get()),
            "toolCallId": str(tool_call_id),
            "phase": event_type,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    event_id = f"{_RUN_ID.get()}:{digest}"
    if len(event_id) <= 128:
        return event_id
    # Run IDs are normally UUIDs, but preserve the <=128 database contract
    # even when an upstream caller supplies an unusually long run ID.
    fallback_material = _RUN_ID.get() + "\0" + identity
    return f"evt:{hashlib.sha256(fallback_material.encode('utf-8')).hexdigest()}"


def build_event(event_type: str, data: dict[str, Any] | None = None, text: str = "") -> dict[str, Any]:
    sync_runtime_event_context()
    data = dict(data or {})
    # Source identity belongs to the envelope and is derived from the active
    # RunnableConfig. Do not allow individual tools to create a second,
    # potentially conflicting copy inside event.data.
    data.pop("sourceScope", None)
    data.pop("sourceNamespace", None)
    tool_call_id = data.pop("toolCallId", None) or _ACTIVE_TOOL_CALL_ID.get()
    event_type = {
        "tool_started": "tool.started",
        "tool_completed": "tool.completed",
        "tool_failed": "tool.failed",
        "draft_created": "draft.created",
        "conflict_blocked": "tool.completed",
    }.get(event_type, event_type)
    sequence_hint = _SEQUENCE_HINT.get() + 1
    _SEQUENCE_HINT.set(sequence_hint)
    text = plain_event_text(text)
    event_id = data.pop("eventId", None) or _canonical_event_id(event_type, tool_call_id)
    return {
        "eventId": str(event_id or uuid4()),
        "runId": _RUN_ID.get(),
        "threadId": _THREAD_ID.get(),
        "tenantId": _TENANT_ID.get(),
        "userId": int(_USER_ID.get()) if _USER_ID.get().isdigit() else _USER_ID.get(),
        "conversationId": _CONVERSATION_ID.get(),
        "messageId": _MESSAGE_ID.get(),
        "taskId": _TASK_ID.get(),
        "sourceScope": _SOURCE_SCOPE.get(),
        "sourceNamespace": list(_SOURCE_NAMESPACE.get()),
        **({"toolCallId": str(tool_call_id)} if tool_call_id else {}),
        # This is diagnostic information only. Java/PostgreSQL assigns the
        # authoritative persisted order and exposes an event cursor. Keeping
        # the local value under a different name prevents parallel Tool
        # contexts from being mistaken for a global sequence.
        "sequenceHint": sequence_hint,
        "type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "durationMs": data.pop("durationMs", 0),
        "data": {
            **({"success": not event_type.endswith("failed")} if event_type else {}),
            **(data or {}),
            **({"text": text} if text else {}),
        },
    }


def emit(writer: Any, event_type: str, text: str, *, require_persist: bool = False, **data: Any) -> dict[str, Any]:
    """发送统一事件；持久化失败只影响审计，不阻断业务 Agent。"""
    sync_runtime_event_context()
    # eventId is an envelope field. Pull it out before forwarding the custom
    # writer payload so it cannot be duplicated inside event.data or the
    # writer's presentation kwargs.
    event_id = data.pop("eventId", None)
    tool_name = data.get("toolName")
    if data.get("toolCallId"):
        bind_tool_call_id(str(data["toolCallId"]))
    elif tool_name:
        if not _ACTIVE_TOOL_CALL_ID.get():
            _ACTIVE_TOOL_CALL_ID.set(f"local:{_RUN_ID.get()}:{tool_name}:{uuid4().hex}")
        data["toolCallId"] = _ACTIVE_TOOL_CALL_ID.get()
    # Tool 是服务端最早可观测的生命周期节点。补一条正式的 run.started，
    # 让刷新恢复时可以使用生命周期时间，而不是猜测首尾工具事件时间。
    if event_type not in {"run.created", "run.started"} and not _RUN_STARTED_EMITTED.get():
        _RUN_STARTED_EMITTED.set(True)
        started = build_event("run.started", {"source": "agent_tool"}, "Agent 开始执行")
        # Tool calls run in separate execution contexts. A deterministic event
        # ID makes the Java/PostgreSQL unique constraint collapse repeated
        # lifecycle notifications into one durable run.started event.
        started["eventId"] = f"{started['runId']}:started"
        if writer:
            writer({"type": "agent_event", "event": started, "text": "Agent 开始执行"})
        try:
            from .http_client import persist_agent_event
            persist_agent_event(started)
        except Exception:
            pass

    event_data = dict(data)
    # Domain tools still emit their legacy card metadata.  Normalize the
    # metadata at the shared event boundary so persisted/replayed results all
    # expose the same renderer-independent presentation contract.
    if "presentation" in event_data:
        event_data["presentation"] = normalize_presentation(
            event_data.get("presentation"),
            data=event_data.get("result") or event_data.get("data"),
        )
    if event_id:
        event_data["eventId"] = event_id
    event = build_event(event_type, event_data, text)
    if writer:
        writer({"type": "agent_event", "event": event, "text": plain_event_text(text), **data})
    try:
        from .http_client import persist_agent_event
        persist_agent_event(event)
    except Exception:
        if require_persist:
            raise
        pass
    return event


def _narration_category(stage: str) -> str:
    return {
        "plan": "plan",
        "draft": "result",
        "confirmation_required": "confirmation",
    }.get(stage, "progress")


def _narration_parent_lineage(namespace: tuple[str, ...] | None = None,
                              *, tool_execution: bool = False) -> tuple[str, ...]:
    """Return the stable parent-graph lineage for a narration entry.

    A model call and the Tool it requests are sibling executions beneath the
    same Agent graph, but LangGraph assigns each sibling a different terminal
    checkpoint segment, for example::

        tools:delegate-a|model:<model-run>
        tools:delegate-a|tools:<tool-run>

    Neither terminal segment is an identity of the user-visible narration.
    The *parent lineage* (``tools:delegate-a`` in the example) is.  At the
    root graph both values reduce to ``()``.  Keeping the preceding segments
    is essential: sibling sub-agents can legitimately reuse
    ``functions.report_progress:0`` in the same Run and must not overwrite
    each other.

    Some older runtimes expose a model call directly at its parent
    ``tools:<delegate>`` namespace rather than adding a ``model:`` segment.
    We deliberately preserve that segment for model streaming.  The Tool
    path, however, always owns one additional final ``tools:`` segment, so it
    is removed only when handling the Tool execution.
    """
    value = tuple(namespace if namespace is not None else _SOURCE_NAMESPACE.get())
    if not value:
        return ()

    final_segment = value[-1]
    if final_segment.startswith("model:"):
        return value[:-1]
    if tool_execution and final_segment.startswith("tools:"):
        return value[:-1]
    return value


def _narration_entry_id(tool_call_id: str | None, *, tool_execution: bool = False) -> str:
    """Create an opaque, retry-stable entry ID for model chunks and the Tool."""
    if not tool_call_id:
        # A streamed chunk without a provider call ID cannot safely be paired
        # with a later Tool execution.  Do not guess from text or ordering;
        # emit an isolated entry instead of risking two concurrent calls
        # corrupting one another. ``report_progress`` itself receives an
        # InjectedToolCallId in production.
        return f"nar:{uuid4()}"
    identity = json.dumps(
        {
            "parentLineage": list(_narration_parent_lineage(tool_execution=tool_execution)),
            "toolCallId": str(tool_call_id),
            "phase": "narration.entry",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    run_id = _RUN_ID.get()
    event_id = f"{run_id}:{digest}"
    if len(event_id) <= 128:
        return event_id
    overflow_material = run_id + "\0" + identity
    return "nar:" + hashlib.sha256(overflow_material.encode("utf-8")).hexdigest()


def _narration_actor(*, tool_execution: bool = False) -> str:
    return "sub_agent" if _narration_parent_lineage(tool_execution=tool_execution) else "main_agent"


def _ensure_narration_run_started(writer: Any) -> None:
    if _RUN_STARTED_EMITTED.get():
        return
    # Keep lifecycle/audit facts separate from the narration timeline.
    _RUN_STARTED_EMITTED.set(True)
    emit(writer, "run.started", "Agent 开始执行", require_persist=True)


def _next_narration_revision(entry_id: str, text: str, *, completed: bool,
                             throttled: bool) -> int | None:
    """Reserve the next revision, or skip a redundant/throttled snapshot."""
    return next_revision(
        entry_id,
        text,
        completed=completed,
        throttled=throttled,
        min_interval_seconds=_NARRATION_STREAM_MIN_INTERVAL_SECONDS,
        min_new_characters=_NARRATION_STREAM_MIN_NEW_CHARACTERS,
    )


def _build_narration_event(*, entry_id: str, revision: int, stage: str,
                           message: str, status: str, actor: str) -> dict[str, Any]:
    event = build_event(
        "narration.upsert",
        {
            "eventId": entry_id,
            "entryId": entry_id,
            "revision": revision,
            "actor": actor,
            "category": _narration_category(stage),
            "status": status,
            "stage": stage,
        },
        message,
    )
    # The canonical narration fields live at the envelope level. ``data``
    # keeps the legacy text projection so historical consumers remain safe.
    event.update({
        "schemaVersion": 1,
        "entryId": entry_id,
        "revision": revision,
        "actor": actor,
        "actorName": _TASK_ID.get() or None,
        "category": _narration_category(stage),
        "status": status,
        "text": message,
    })
    # These values remain available in tool/audit lifecycle events. A
    # narration must not give the frontend a second identity vocabulary.
    event.pop("toolCallId", None)
    event.pop("sourceScope", None)
    event.pop("sourceNamespace", None)
    return event


def publish_streaming_narration(writer: Any, *, stage: str, message: str,
                                tool_call_id: str | None) -> dict[str, Any] | None:
    """Publish one throttled, full-text snapshot from model Tool-call chunks.

    This function is deliberately called *before* ``report_progress`` runs.
    It uses the same opaque entry ID as the eventual Tool invocation; the Tool
    then writes the terminal ``completed`` snapshot in place.
    """
    sync_runtime_event_context()
    text = plain_event_text(message[:300])
    if not text:
        return None
    if stage not in {"plan", "agent_message", "draft", "confirmation_required"}:
        stage = "agent_message"
    _ensure_narration_run_started(writer)
    entry_id = _narration_entry_id(tool_call_id)
    revision = _next_narration_revision(entry_id, text, completed=False, throttled=True)
    if revision is None:
        return None
    event = _build_narration_event(
        entry_id=entry_id,
        revision=revision,
        stage=stage,
        message=text,
        status="streaming",
        actor=_narration_actor(),
    )
    from .http_client import persist_agent_event
    return NarrationPublisher(persist_agent_event).publish(writer, event)


def publish_model_narration(writer: Any, *, message: str, model_call_id: str,
                            completed: bool = False) -> dict[str, Any] | None:
    """Publish the complete text of a sub-agent model response incrementally.

    Unlike ``report_progress``, this path intentionally does not cap the text:
    the child model output is the user-requested full summary.  The same model
    call ID addresses every revision, so the browser updates one row in place.
    """
    sync_runtime_event_context()
    text = plain_event_text(message)
    if not text:
        return None
    _ensure_narration_run_started(writer)
    entry_id = _narration_entry_id(model_call_id)
    revision = _next_narration_revision(
        entry_id, text, completed=completed, throttled=not completed,
    )
    if revision is None:
        return None
    event = _build_narration_event(
        entry_id=entry_id,
        revision=revision,
        stage="agent_message",
        message=text,
        status="completed" if completed else "streaming",
        actor=_narration_actor(),
    )
    from .http_client import persist_agent_event
    return NarrationPublisher(persist_agent_event).publish(writer, event)


def publish_narration(writer: Any, *, stage: str, message: str,
                      tool_call_id: str | None) -> dict[str, Any]:
    """Persist and then stream the sole user-visible process summary.

    ``toolCallId`` and graph namespaces remain internal only.  They are used
    to build a retry-stable opaque entry ID, but are deliberately absent from
    the narration contract consumed by the browser.
    """
    sync_runtime_event_context()
    _ensure_narration_run_started(writer)

    _, effective_stage = progress_event_type(stage)
    text = plain_event_text(message[:300])
    entry_id = _narration_entry_id(tool_call_id, tool_execution=True)
    revision = _next_narration_revision(entry_id, text, completed=True, throttled=False)
    # A duplicate Tool retry may arrive after the completed snapshot. It is
    # already durable, so preserve the existing revision for the idempotent
    # acknowledgement instead of creating a second timeline row.
    if revision is None:
        revision = current_revision(entry_id)
    event = _build_narration_event(
        entry_id=entry_id,
        revision=revision,
        stage=effective_stage,
        message=text,
        status="completed",
        actor=_narration_actor(tool_execution=True),
    )
    from .http_client import persist_agent_event
    return NarrationPublisher(persist_agent_event).publish(writer, event)


@tool
def report_progress(
    stage: str,
    message: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> ToolResponse:
    """向用户播报当前执行计划或业务处理进度，不执行任何业务写操作。

    主 Agent 对业务请求的首个 Tool Call 必须使用 stage=plan，让摘要先
    通过流式事件到达前端，再继续后续路由和业务处理。
    """
    bind_tool_call_id(tool_call_id)
    if stage not in {"plan", "agent_message", "draft", "confirmation_required"}:
        stage = "agent_message"
    event = publish_narration(
        get_stream_writer(), stage=stage, message=message, tool_call_id=tool_call_id,
    )
    return tool_success({
        "recorded": True,
        "entryId": event["entryId"],
        "stage": event["data"].get("stage", stage),
        "message": message[:300],
    })
