"""Server-side extraction of ``report_progress`` narration.

LangChain's agent runner invokes its model with ``ainvoke``/``invoke`` even
when the outer LangGraph run is streamed.  This adapter consumes the bound
model's own chunks, publishes ``report_progress.message`` snapshots, and then
returns the exact merged AI message the agent would otherwise receive.
The browser consequently never needs to inspect model tool-call chunks.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, message_chunk_to_message

from ..tools.common.events import (
    narration_validation_issues,
    new_final_answer_entry_id,
    publish_final_answer_stream,
    publish_streaming_narration,
)


_STREAM_MODEL_OUTPUT: ContextVar[bool] = ContextVar(
    "kodagent_stream_model_output", default=False
)
_FINAL_ANSWER_ENTRY_ID: ContextVar[str | None] = ContextVar(
    "kodagent_final_answer_entry_id", default=None
)


def stream_model_output_enabled() -> bool:
    return _STREAM_MODEL_OUTPUT.get()


def current_final_answer_entry_id() -> str | None:
    """返回当前收尾调用的最终答案标识。"""

    return _FINAL_ANSWER_ENTRY_ID.get()


@contextmanager
def stream_model_output_scope(enabled: bool = True, *, entry_id: str | None = None):
    """开启一次主 Agent 收尾的流式输出，并固定其 checkpoint 关联标识。"""

    token = _STREAM_MODEL_OUTPUT.set(enabled)
    inherited = _FINAL_ANSWER_ENTRY_ID.get()
    effective_entry_id = (
        str(entry_id or inherited or new_final_answer_entry_id(uuid4().hex)).strip()
        if enabled else None
    )
    entry_token = _FINAL_ANSWER_ENTRY_ID.set(effective_entry_id)
    try:
        yield effective_entry_id
    finally:
        _STREAM_MODEL_OUTPUT.reset(token)
        _FINAL_ANSWER_ENTRY_ID.reset(entry_token)


_STAGE_RE = re.compile(r'"stage"\s*:\s*"([^"\\]*)')
_MESSAGE_START_RE = re.compile(r'"message"\s*:\s*"')
_VISIBLE_STAGES = {"plan", "agent_message", "draft", "confirmation_required"}


def _args_fragment(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        # A few OpenAI-compatible providers emit an already-decoded object in
        # a single Tool Call chunk. Serialising it restores the same parser
        # path without changing what the model receives.
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return ""


def _decode_partial_json_string(value: str) -> str:
    """Decode the visible prefix of a JSON string without accepting bad JSON.

    The Tool arguments are incomplete for most chunks. ``json.loads`` alone
    therefore cannot be used; this small decoder only emits complete escapes
    and leaves an unfinished escape/unicode sequence out until the next chunk.
    """
    output: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char != "\\":
            output.append(char)
            index += 1
            continue
        if index + 1 >= len(value):
            break
        escaped = value[index + 1]
        replacements = {"\"": '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
        if escaped == "u":
            raw = value[index + 2:index + 6]
            if len(raw) < 4 or any(item not in "0123456789abcdefABCDEF" for item in raw):
                break
            output.append(chr(int(raw, 16)))
            index += 6
            continue
        replacement = replacements.get(escaped)
        if replacement is None:
            # Invalid JSON escaping must never become user-visible text.
            break
        output.append(replacement)
        index += 2
    return "".join(output)


def _partial_message(args: str) -> str | None:
    """Return the current complete text prefix of a report_progress message."""
    try:
        decoded = json.loads(args)
    except (TypeError, ValueError, json.JSONDecodeError):
        decoded = None
    if isinstance(decoded, dict) and isinstance(decoded.get("message"), str):
        return decoded["message"]

    match = _MESSAGE_START_RE.search(args)
    if match is None:
        return None
    raw = args[match.end():]
    # Discard the closing quote and later fields if the message happens to be
    # complete while a provider is still streaming metadata after it.
    closing = False
    escaped = False
    for index, char in enumerate(raw):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            raw = raw[:index]
            closing = True
            break
    text = _decode_partial_json_string(raw)
    # An empty prefix is not visible and frequently precedes the first real
    # token. Returning None also avoids a blank transient Process item.
    return text if text.strip() or closing and text else None


def _partial_stage(args: str) -> str:
    try:
        decoded = json.loads(args)
    except (TypeError, ValueError, json.JSONDecodeError):
        decoded = None
    if isinstance(decoded, dict) and str(decoded.get("stage") or "") in _VISIBLE_STAGES:
        return str(decoded["stage"])
    match = _STAGE_RE.search(args)
    stage = match.group(1) if match else "agent_message"
    return stage if stage in _VISIBLE_STAGES else "agent_message"


@dataclass
class _PartialToolCall:
    index: int
    name: str | None = None
    tool_call_id: str | None = None
    args: str = ""
    last_text: str = ""


class ReportProgressChunkTracker:
    """Accumulate one model response's partial Tool Call arguments safely."""

    def __init__(self) -> None:
        self._calls: dict[int, _PartialToolCall] = {}

    def observe(self, message: Any) -> None:
        for position, item in enumerate(getattr(message, "tool_call_chunks", None) or []):
            if not isinstance(item, dict):
                continue
            raw_index = item.get("index", position)
            try:
                index = int(raw_index)
            except (TypeError, ValueError):
                index = position
            call = self._calls.setdefault(index, _PartialToolCall(index=index))
            if item.get("name"):
                call.name = str(item["name"])
            if item.get("id"):
                call.tool_call_id = str(item["id"])
            fragment = _args_fragment(item.get("args"))
            if fragment:
                # Chat Completions usually sends deltas, while a few
                # compatible gateways repeat the whole accumulated argument
                # string in every chunk. Support both without corrupting the
                # partial JSON buffer.
                call.args = fragment if call.args and fragment.startswith(call.args) else call.args + fragment
            if call.name != "report_progress" or not call.tool_call_id:
                continue
            text = _partial_message(call.args)
            if text is None or text == call.last_text:
                continue
            if narration_validation_issues(text):
                continue
            call.last_text = text
            self._publish(call, text)

    @staticmethod
    def _publish(call: _PartialToolCall, text: str) -> None:
        # A streamed prefix may arrive before the model finishes its tool
        # arguments. Never expose a prefix that already contains protocol
        # fields; keep the last accepted text so a later valid snapshot can
        # still be published on the same entry and revision sequence.
        if narration_validation_issues(text):
            return
        try:
            from langgraph.config import get_stream_writer

            writer = get_stream_writer()
        except Exception:
            # The wrapper is also usable in direct invoke tests and offline
            # jobs. In that context no custom stream writer exists; durable
            # persistence still receives the canonical snapshot.
            writer = None
        publish_streaming_narration(
            writer,
            stage=_partial_stage(call.args),
            message=text,
            tool_call_id=call.tool_call_id,
        )


def _content_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "".join(parts)


def _provider_safe_input(value: Any) -> Any:
    """Preserve the provider tool-call protocol across LangGraph turns.

    SiliconFlow thinking models require ``reasoning_content`` on an assistant
    message that contains tool calls when that message is replayed. LangChain's
    OpenAI-compatible parser does not expose the provider field, so a normal
    tool loop can otherwise fail on its second model request. An empty field is
    intentional: it satisfies the wire contract without fabricating reasoning
    text. Work on a deep copy so checkpoint state and UI history stay unchanged.
    """
    if not isinstance(value, list):
        return value
    copied = deepcopy(value)
    for message in copied:
        if isinstance(message, dict):
            if str(message.get("type") or "").lower() != "ai" or not message.get("tool_calls"):
                continue
            additional = dict(message.get("additional_kwargs") or {})
            # Some OpenAI-compatible serializers omit empty optional fields.
            additional.setdefault("reasoning_content", " ")
            message["additional_kwargs"] = additional
            continue
        if getattr(message, "type", "") != "ai" or not getattr(message, "tool_calls", None):
            continue
        additional = dict(getattr(message, "additional_kwargs", {}) or {})
        additional.setdefault("reasoning_content", " ")
        message.additional_kwargs = additional
    return copied


class ModelOutputChunkTracker:
    """仅在主 Agent 收尾范围内直播最终回答的全量快照。

    这个 tracker 不改变模型返回值，仍由 ``_merge_message_chunks`` 生成完整
    ``AIMessage`` 写回图。它也不承担过程播报：``report_progress`` 继续由
    ``ReportProgressChunkTracker`` 处理。收尾调用的工具面板已由计划投影层清空；
    此处仍以 ``saw_tool_call`` 作防御，确保异常工具调用不会被当作最终文本直播。
    """

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.model_call_id = f"model-output:{uuid4()}"
        self.final_entry_id = current_final_answer_entry_id()
        self.text = ""
        self.last_text = ""
        self.saw_tool_call = False

    def observe(self, message: Any) -> None:
        if not self.enabled:
            return
        if getattr(message, "tool_call_chunks", None):
            self.saw_tool_call = True
            return
        if self.saw_tool_call:
            return
        fragment = _content_text(message)
        if not fragment:
            return
        # Compatible gateways differ between delta text and cumulative text.
        self.text = fragment if self.text and fragment.startswith(self.text) else self.text + fragment
        if self.text == self.last_text:
            return
        self.last_text = self.text
        self._publish(completed=False)

    def complete(self) -> None:
        if self.enabled and not self.saw_tool_call and self.text:
            self._publish(completed=True)

    def _publish(self, *, completed: bool) -> None:
        try:
            from langgraph.config import get_stream_writer
            writer = get_stream_writer()
        except Exception:
            writer = None
        publish_final_answer_stream(
            writer,
            message=self.text,
            model_call_id=self.model_call_id,
            completed=completed,
            entry_id=self.final_entry_id,
        )


def _merge_message_chunks(chunks: list[Any]) -> Any:
    if not chunks:
        raise ValueError("The model returned no stream chunks")
    first = chunks[0]
    if not isinstance(first, AIMessageChunk):
        # Models that do not implement streaming fall back to one AIMessage.
        # That response is already the exact result AgentFactory expects.
        return first
    merged = first
    for chunk in chunks[1:]:
        if not isinstance(chunk, AIMessageChunk):
            raise TypeError("A streamed chat model yielded a non-AIMessage chunk")
        merged += chunk
    return message_chunk_to_message(merged)


class NarrationStreamingRunnable:
    """Delegate a bound model while publishing canonical narration snapshots."""

    def __init__(
        self,
        runnable: Any,
        *,
        qwen3_extra_body: dict[str, Any] | None = None,
    ):
        self._runnable = runnable
        self._qwen3_extra_body = qwen3_extra_body

    def __getattr__(self, name: str) -> Any:
        return getattr(self._runnable, name)

    def stream(self, input: Any, config: Any = None, **kwargs: Any) -> Iterator[Any]:
        tracker = ReportProgressChunkTracker()
        # 最终回答流只能由计划投影层的收尾范围开启；不能由模型包装器实例
        # 自行配置，以免子 Agent 或常规路由回合意外把自由文本推到前端。
        output_tracker = ModelOutputChunkTracker(stream_model_output_enabled())
        input = _provider_safe_input(input)
        try:
            # Only Qwen3 carries a provider-specific request body.  Do not
            # inject thinking controls into OpenAI or other compatible models.
            if self._qwen3_extra_body is not None:
                kwargs.setdefault("extra_body", self._qwen3_extra_body)
            for chunk in self._runnable.stream(input, config=config, **kwargs):
                tracker.observe(chunk)
                output_tracker.observe(chunk)
                yield chunk
        finally:
            output_tracker.complete()

    async def astream(self, input: Any, config: Any = None, **kwargs: Any) -> AsyncIterator[Any]:
        tracker = ReportProgressChunkTracker()
        output_tracker = ModelOutputChunkTracker(stream_model_output_enabled())
        input = _provider_safe_input(input)
        try:
            if self._qwen3_extra_body is not None:
                kwargs.setdefault("extra_body", self._qwen3_extra_body)
            async for chunk in self._runnable.astream(input, config=config, **kwargs):
                tracker.observe(chunk)
                output_tracker.observe(chunk)
                yield chunk
        finally:
            output_tracker.complete()

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        return _merge_message_chunks(list(self.stream(input, config=config, **kwargs)))

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        chunks = [chunk async for chunk in self.astream(input, config=config, **kwargs)]
        return _merge_message_chunks(chunks)


class NarrationStreamingModel:
    """A transparent ChatModel facade that preserves binding APIs.

    AgentFactory invokes ``bind_tools(...).ainvoke(...)``. Wrapping *after*
    binding is crucial: the original provider still owns tool schemas and
    parsing while this facade only observes its chunks.
    """

    def __init__(
        self,
        model: Any,
        *,
        qwen3_extra_body: dict[str, Any] | None = None,
    ):
        self._model = model
        self._qwen3_extra_body = qwen3_extra_body

    def __getattr__(self, name: str) -> Any:
        return getattr(self._model, name)

    def bind_tools(self, *args: Any, **kwargs: Any) -> NarrationStreamingRunnable:
        return NarrationStreamingRunnable(
            self._model.bind_tools(*args, **kwargs),
            qwen3_extra_body=self._qwen3_extra_body,
        )

    def bind(self, *args: Any, **kwargs: Any) -> NarrationStreamingRunnable:
        return NarrationStreamingRunnable(
            self._model.bind(*args, **kwargs),
            qwen3_extra_body=self._qwen3_extra_body,
        )
