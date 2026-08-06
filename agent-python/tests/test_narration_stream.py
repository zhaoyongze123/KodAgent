import asyncio

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from src.services.narration_stream import NarrationStreamingModel, ReportProgressChunkTracker, _provider_safe_input
from src.services.model_runtime import _SiliconFlowChatOpenAI
from src.tools.common import events as events_module
from src.tools.common.events import (
    publish_model_narration,
    publish_narration,
    publish_streaming_narration,
    set_event_context,
)


def _progress_chunk(*, args: str, name: str | None = None, call_id: str | None = None, index: int = 0):
    payload = {"args": args, "index": index}
    if name is not None:
        payload["name"] = name
    if call_id is not None:
        payload["id"] = call_id
    return AIMessageChunk(content="", tool_call_chunks=[payload])


def test_report_progress_chunks_emit_full_text_snapshots(monkeypatch):
    captured = []
    monkeypatch.setattr(
        "src.services.narration_stream.publish_streaming_narration",
        lambda writer, **event: captured.append(event),
    )
    tracker = ReportProgressChunkTracker()

    tracker.observe(_progress_chunk(
        name="report_progress", call_id="progress-1", args='{"stage":"plan","message":"我准备'
    ))
    tracker.observe(_progress_chunk(args="先检查"))

    assert [(item["tool_call_id"], item["stage"], item["message"]) for item in captured] == [
        ("progress-1", "plan", "我准备"),
        ("progress-1", "plan", "我准备先检查"),
    ]


def test_non_progress_tool_or_plain_text_never_becomes_narration(monkeypatch):
    captured = []
    monkeypatch.setattr(
        "src.services.narration_stream.publish_streaming_narration",
        lambda writer, **event: captured.append(event),
    )
    tracker = ReportProgressChunkTracker()

    tracker.observe(AIMessageChunk(content="普通 AI 回复"))
    tracker.observe(_progress_chunk(name="list_available_meeting_rooms", call_id="rooms-1", args='{"x":"文本"}'))

    assert captured == []


def test_provider_safe_input_adds_empty_reasoning_content_without_mutating_state():
    assistant = AIMessage(content="", tool_calls=[{"name": "report_progress", "args": {}, "id": "call-1"}])
    messages = [HumanMessage(content="开始"), assistant, ToolMessage(content="完成", tool_call_id="call-1")]

    safe = _provider_safe_input(messages)

    assert safe is not messages
    assert safe[1].additional_kwargs["reasoning_content"] == " "
    assert "reasoning_content" not in assistant.additional_kwargs


def test_siliconflow_payload_serializes_reasoning_content_at_wire_boundary():
    model = _SiliconFlowChatOpenAI(
        model="kimi-test",
        api_key="test-key",
        base_url="https://api.siliconflow.cn/v1",
        extra_body={"enable_thinking": False},
        use_responses_api=False,
    )
    assistant = AIMessage(
        content="",
        tool_calls=[{"name": "report_progress", "args": {}, "id": "call-1"}],
    )

    payload = model._get_request_payload([HumanMessage(content="开始"), assistant])

    assert payload["extra_body"] == {"enable_thinking": False}
    assert payload["messages"][1]["reasoning_content"] == " "
    assert "reasoning_content" not in assistant.additional_kwargs


def test_siliconflow_payload_preserves_provider_reasoning_content():
    model = _SiliconFlowChatOpenAI(
        model="kimi-test",
        api_key="test-key",
        base_url="https://api.siliconflow.cn/v1",
        use_responses_api=False,
    )
    assistant = AIMessage(
        content="",
        additional_kwargs={"reasoning_content": "provider trace"},
        tool_calls=[{"name": "report_progress", "args": {}, "id": "call-1"}],
    )

    payload = model._get_request_payload([assistant])

    assert payload["messages"][0]["reasoning_content"] == "provider trace"


class _BoundModel:
    def __init__(self, chunks):
        self._chunks = chunks

    def stream(self, input, config=None, **kwargs):
        yield from self._chunks

    async def astream(self, input, config=None, **kwargs):
        for chunk in self._chunks:
            yield chunk


class _ToolBindableModel:
    def __init__(self, chunks):
        self._chunks = chunks
        self.bound_tools = None

    def bind_tools(self, tools, **kwargs):
        self.bound_tools = (tools, kwargs)
        return _BoundModel(self._chunks)

    def bind(self, **kwargs):
        return _BoundModel(self._chunks)


def test_wrapper_preserves_tool_binding_and_merged_tool_call(monkeypatch):
    captured = []
    monkeypatch.setattr(
        "src.services.narration_stream.publish_streaming_narration",
        lambda writer, **event: captured.append(event),
    )
    model = _ToolBindableModel([
        _progress_chunk(
            name="report_progress",
            call_id="call-progress",
            args='{"stage":"plan","message":"开始处理"}',
        ),
        AIMessageChunk(content="", chunk_position="last"),
    ])

    result = NarrationStreamingModel(model).bind_tools([{"type": "function", "function": {"name": "report_progress"}}]).invoke([])

    assert model.bound_tools[0][0]["function"]["name"] == "report_progress"
    assert result.tool_calls == [{"name": "report_progress", "args": {"stage": "plan", "message": "开始处理"}, "id": "call-progress", "type": "tool_call"}]
    assert captured[-1]["message"] == "开始处理"


def test_wrapper_async_preserves_tool_call(monkeypatch):
    captured = []
    monkeypatch.setattr(
        "src.services.narration_stream.publish_streaming_narration",
        lambda writer, **event: captured.append(event),
    )
    model = _ToolBindableModel([
        _progress_chunk(
            name="report_progress",
            call_id="async-progress",
            args='{"stage":"agent_message","message":"正在处理"}',
        ),
        AIMessageChunk(content="", chunk_position="last"),
    ])

    result = asyncio.run(NarrationStreamingModel(model).bind_tools([]).ainvoke([]))

    assert result.tool_calls[0]["id"] == "async-progress"
    assert captured[-1]["message"] == "正在处理"


def test_subagent_model_output_streams_full_text_and_completes_same_entry(monkeypatch):
    captured = []
    monkeypatch.setattr(
        "src.services.narration_stream.publish_model_narration",
        lambda writer, **event: captured.append(event),
    )
    model = _ToolBindableModel([
        AIMessageChunk(content="当前用户的待办审批列表如下："),
        AIMessageChunk(content="共有 23 条待办事项。"),
        AIMessageChunk(content="最后一条也必须完整保留。"),
    ])

    result = NarrationStreamingModel(model, stream_model_output=True).bind_tools([]).invoke([])

    assert result.content == "当前用户的待办审批列表如下：共有 23 条待办事项。最后一条也必须完整保留。"
    assert captured
    assert captured[-1]["completed"] is True
    assert captured[-1]["message"] == result.content
    assert len({item["model_call_id"] for item in captured}) == 1


def test_model_narration_persistence_does_not_truncate_full_output(monkeypatch):
    persisted = []
    monkeypatch.setattr(
        "src.tools.common.http_client.persist_agent_event",
        lambda event, **kwargs: persisted.append(event.copy()) or {
            "eventId": event["eventId"],
            "eventCursor": {"cursor": len(persisted)},
        },
    )
    set_event_context("run-full-output", "thread-full-output")
    text = "审批结果：" + ("详细内容。" * 120)

    event = publish_model_narration(
        None,
        message=text,
        model_call_id="child-model-output",
        completed=True,
    )

    assert event is not None
    assert event["text"] == text
    assert len(event["text"]) > 300


def test_main_agent_model_output_is_not_published_as_process_narration(monkeypatch):
    captured = []
    monkeypatch.setattr(
        "src.services.narration_stream.publish_model_narration",
        lambda writer, **event: captured.append(event),
    )
    model = _ToolBindableModel([AIMessageChunk(content="主 Agent 最终答案")])

    NarrationStreamingModel(model).bind_tools([]).invoke([])

    assert captured == []


def test_streaming_and_final_tool_share_entry_and_revision(monkeypatch):
    persisted = []
    streamed = []

    def persist(event, **kwargs):
        persisted.append(event.copy())
        return {"eventId": event["eventId"], "eventCursor": {"cursor": 42, "eventId": event["eventId"]}}

    monkeypatch.setattr("src.tools.common.http_client.persist_agent_event", persist)
    set_event_context("run-stream-final", "thread-stream-final", message_id="message-stream-final")

    first = publish_streaming_narration(streamed.append, stage="plan", message="我准备", tool_call_id="call-1")
    second = publish_streaming_narration(streamed.append, stage="plan", message="我准备先检查会议室可预约性", tool_call_id="call-1")
    final = publish_narration(streamed.append, stage="plan", message="我准备先检查会议室可预约性", tool_call_id="call-1")

    assert first and second
    assert first["entryId"] == second["entryId"] == final["entryId"]
    assert (first["revision"], second["revision"], final["revision"]) == (1, 2, 3)
    assert first["status"] == second["status"] == "streaming"
    assert final["status"] == "completed"


def test_root_model_and_tool_namespaces_update_one_entry(monkeypatch):
    monkeypatch.setattr(
        "src.tools.common.http_client.persist_agent_event",
        lambda event, **kwargs: {"eventId": event["eventId"], "eventCursor": {"cursor": 1}},
    )
    set_event_context("run-root-model-tool", "thread-root-model-tool")

    # LangGraph gives the sibling model and Tool executions different opaque
    # terminal checkpoint segments. They must still address the root entry.
    events_module._SOURCE_NAMESPACE.set(("model:model-run-7",))
    streamed = publish_streaming_narration(
        None, stage="plan", message="正在确认预约信息", tool_call_id="functions.report_progress:0"
    )
    events_module._SOURCE_NAMESPACE.set(("tools:tool-run-7",))
    completed = publish_narration(
        None, stage="plan", message="正在确认预约信息", tool_call_id="functions.report_progress:0"
    )

    assert streamed and completed
    assert streamed["entryId"] == completed["entryId"]
    assert (streamed["revision"], completed["revision"]) == (1, 2)
    assert (streamed["actor"], completed["actor"]) == ("main_agent", "main_agent")


def test_distinct_tool_call_ids_never_share_a_root_entry(monkeypatch):
    monkeypatch.setattr(
        "src.tools.common.http_client.persist_agent_event",
        lambda event, **kwargs: {"eventId": event["eventId"], "eventCursor": {"cursor": 1}},
    )
    set_event_context("run-distinct-progress-calls", "thread-distinct-progress-calls")
    events_module._SOURCE_NAMESPACE.set(("model:model-run",))
    first = publish_streaming_narration(None, stage="plan", message="第一条", tool_call_id="functions.report_progress:0")
    second = publish_streaming_narration(None, stage="plan", message="第二条", tool_call_id="functions.report_progress:1")

    assert first and second
    assert first["entryId"] != second["entryId"]


def test_subagent_streams_do_not_cross_entry_ids(monkeypatch):
    monkeypatch.setattr(
        "src.tools.common.http_client.persist_agent_event",
        lambda event, **kwargs: {"eventId": event["eventId"], "eventCursor": {"cursor": 1}},
    )
    set_event_context("run-parallel", "thread-parallel", message_id="message-parallel")
    events_module._SOURCE_NAMESPACE.set(("tools:task-a",))
    events_module._SOURCE_SCOPE.set("subgraph")
    left = publish_streaming_narration(None, stage="plan", message="子任务 A", tool_call_id="same-call")
    events_module._SOURCE_NAMESPACE.set(("tools:task-b",))
    right = publish_streaming_narration(None, stage="plan", message="子任务 B", tool_call_id="same-call")

    assert left and right
    assert left["entryId"] != right["entryId"]


def test_subagent_tool_completion_updates_its_model_stream_entry(monkeypatch):
    monkeypatch.setattr(
        "src.tools.common.http_client.persist_agent_event",
        lambda event, **kwargs: {"eventId": event["eventId"], "eventCursor": {"cursor": 1}},
    )
    set_event_context("run-subagent-final", "thread-subagent-final", message_id="message-subagent-final")
    events_module._SOURCE_SCOPE.set("subgraph")
    # Model and Tool have distinct terminal runtime segments below the same
    # parent sub-agent lineage.
    events_module._SOURCE_NAMESPACE.set(("tools:parent-task", "model:model-run"))
    streamed = publish_streaming_narration(None, stage="agent_message", message="子 Agent 正在处理", tool_call_id="progress-call")
    events_module._SOURCE_NAMESPACE.set(("tools:parent-task", "tools:tool-run"))
    completed = publish_narration(None, stage="agent_message", message="子 Agent 正在处理", tool_call_id="progress-call")

    assert streamed and streamed["entryId"] == completed["entryId"]
    assert (streamed["revision"], completed["revision"]) == (1, 2)
    assert (streamed["actor"], completed["actor"]) == ("sub_agent", "sub_agent")
    assert streamed["status"] == "streaming"
    assert completed["status"] == "completed"


def test_sibling_subagents_reusing_tool_call_id_do_not_cross_entries(monkeypatch):
    monkeypatch.setattr(
        "src.tools.common.http_client.persist_agent_event",
        lambda event, **kwargs: {"eventId": event["eventId"], "eventCursor": {"cursor": 1}},
    )
    set_event_context("run-sibling-subagents", "thread-sibling-subagents")
    events_module._SOURCE_SCOPE.set("subgraph")
    tool_call_id = "functions.report_progress:0"

    events_module._SOURCE_NAMESPACE.set(("tools:delegate-a", "model:model-a"))
    first_stream = publish_streaming_narration(None, stage="plan", message="子任务 A", tool_call_id=tool_call_id)
    events_module._SOURCE_NAMESPACE.set(("tools:delegate-b", "model:model-b"))
    second_stream = publish_streaming_narration(None, stage="plan", message="子任务 B", tool_call_id=tool_call_id)

    events_module._SOURCE_NAMESPACE.set(("tools:delegate-a", "tools:tool-a"))
    first_final = publish_narration(None, stage="plan", message="子任务 A", tool_call_id=tool_call_id)
    events_module._SOURCE_NAMESPACE.set(("tools:delegate-b", "tools:tool-b"))
    second_final = publish_narration(None, stage="plan", message="子任务 B", tool_call_id=tool_call_id)

    assert first_stream and second_stream and first_final and second_final
    assert first_stream["entryId"] == first_final["entryId"]
    assert second_stream["entryId"] == second_final["entryId"]
    assert first_stream["entryId"] != second_stream["entryId"]
    assert (first_final["revision"], second_final["revision"]) == (2, 2)
