from src.tools.party_files import metadata


def test_metadata_plan_delegates_authorized_query_to_java(monkeypatch):
    emitted = []
    monkeypatch.setattr(metadata, "get_stream_writer", lambda: object())
    monkeypatch.setattr(metadata, "emit", lambda *args, **kwargs: emitted.append((args, kwargs)))
    calls = []
    monkeypatch.setattr(
        metadata,
        "java_post",
        lambda path, payload: calls.append((path, payload)) or {
            "status": "READY",
            "totalScanned": 8,
            "totalMatched": 1,
            "matches": [{"id": 8, "title": "制度通知", "publishTime": "2026-07-10T09:00:00"}],
        },
    )

    result = metadata.execute_party_file_metadata_plan.func(
        {
            "entity": "party_file",
            "operation": "metadata_query",
            "rank": {"field": "publishTime", "mode": "nearest", "target": "2026-07-10"},
            "limit": 1,
        },
        tool_call_id="plan-call",
    )

    assert result.ok is True
    assert calls[0][0] == "/agent/tools/party-files/query-plan"
    assert result.data["matches"][0]["id"] == 8
    assert emitted[-1][1]["toolName"] == "execute_party_file_metadata_plan"
