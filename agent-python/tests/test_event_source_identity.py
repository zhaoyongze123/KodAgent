import json
from types import SimpleNamespace

from src.tools.common import events


def runnable_config(namespace: str = "") -> dict:
    return {
        "run_id": "run-source-1",
        "configurable": {
            "thread_id": "thread-source-1",
            "checkpoint_ns": namespace,
        },
        "metadata": {},
    }


def test_checkpoint_namespace_maps_to_durable_source_identity():
    assert events.canonical_source_identity(runnable_config()) == ("main", ())
    assert events.canonical_source_identity(
        runnable_config("tools:meeting-task|tools:calendar-task")
    ) == (
        "subgraph",
        ("tools:meeting-task", "tools:calendar-task"),
    )


def test_runtime_execution_info_is_the_primary_namespace_source():
    config = runnable_config("tools:config-value")
    config["configurable"]["__pregel_runtime"] = SimpleNamespace(
        execution_info=SimpleNamespace(checkpoint_ns="tools:runtime-value")
    )

    assert events.canonical_source_identity(config) == (
        "subgraph",
        ("tools:runtime-value",),
    )


def test_build_event_writes_source_identity_to_the_envelope(monkeypatch):
    events.set_event_context("run-source-1", "thread-source-1")
    monkeypatch.setattr(
        events,
        "get_config",
        lambda: runnable_config("tools:meeting-task"),
    )

    event = events.build_event(
        "progress",
        {
            "toolCallId": "functions.report_progress:0",
            "sourceScope": "main",
            "sourceNamespace": ["incorrect"],
        },
        "正在查询会议室",
    )

    assert event["sourceScope"] == "subgraph"
    assert event["sourceNamespace"] == ["tools:meeting-task"]
    assert "sourceScope" not in event["data"]
    assert "sourceNamespace" not in event["data"]


def test_emit_persistence_roundtrip_keeps_source_identity(monkeypatch):
    events.set_event_context("run-source-1", "thread-source-1")
    monkeypatch.setattr(
        events,
        "get_config",
        lambda: runnable_config("tools:meeting-task"),
    )
    persisted: list[dict] = []
    monkeypatch.setattr(
        "src.tools.common.http_client.persist_agent_event",
        lambda event: persisted.append(event),
    )

    event = events.emit(
        lambda _: None,
        "progress",
        "正在查询会议室",
        toolCallId="functions.report_progress:0",
    )
    roundtrip = json.loads(json.dumps(persisted[-1]))

    assert roundtrip["eventId"] == event["eventId"]
    assert roundtrip["sourceScope"] == "subgraph"
    assert roundtrip["sourceNamespace"] == ["tools:meeting-task"]


def test_missing_namespace_never_guesses_a_subgraph():
    config = {
        "run_id": "run-source-1",
        "configurable": {"thread_id": "thread-source-1"},
        "metadata": {},
    }

    assert events.canonical_source_identity(config) == ("main", ())
