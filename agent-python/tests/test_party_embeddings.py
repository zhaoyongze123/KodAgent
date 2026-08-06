from src.services import party_embeddings
from src.tools.party_files import knowledge


def test_siliconflow_defaults_to_qwen_and_rejects_wrong_dimension(monkeypatch):
    calls = []

    class Embeddings:
        def create(self, **kwargs):
            calls.append(kwargs)
            return type("Response", (), {"data": [type("Data", (), {"embedding": [0.1] * 3})()]})()

    monkeypatch.setenv("OA_AGENT_EMBEDDING_PROVIDER", "siliconflow")
    monkeypatch.setenv("OA_AGENT_EMBEDDING_API_KEY", "test-key")
    monkeypatch.delenv("OA_AGENT_EMBEDDING_MODEL", raising=False)
    monkeypatch.setattr(party_embeddings, "_client", lambda: type("Client", (), {"embeddings": Embeddings()})())

    assert party_embeddings.embed_text("制度要求") is None
    assert calls[0]["model"] == "Qwen/Qwen3-VL-Embedding-8B"


def test_knowledge_tool_never_falls_back_to_unscoped_index_when_java_fails(monkeypatch):
    monkeypatch.setenv("OA_AGENT_PARTY_KNOWLEDGE_JAVA", "true")
    monkeypatch.delenv("OA_AGENT_PARTY_KNOWLEDGE_OFFLINE_FALLBACK", raising=False)
    monkeypatch.setattr(knowledge, "get_stream_writer", lambda: object())
    monkeypatch.setattr(knowledge, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(knowledge, "embed_query", lambda query: None)
    monkeypatch.setattr(knowledge, "java_get", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("gateway unavailable")))

    result = knowledge.search_party_knowledge.func(query="三重一大", tool_call_id="call-1")

    assert result.ok is False
    assert result.error.code == "PARTY_KNOWLEDGE_UNAVAILABLE"


def test_knowledge_tool_allows_offline_index_only_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("OA_AGENT_PARTY_KNOWLEDGE_JAVA", "true")
    monkeypatch.setenv("OA_AGENT_PARTY_KNOWLEDGE_OFFLINE_FALLBACK", "true")
    monkeypatch.setattr(knowledge, "get_stream_writer", lambda: object())
    monkeypatch.setattr(knowledge, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(knowledge, "embed_query", lambda query: None)
    monkeypatch.setattr(knowledge, "java_get", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("gateway unavailable")))
    monkeypatch.setattr(
        knowledge,
        "configured_index",
        lambda: type("Index", (), {"search": lambda self, *args, **kwargs: {"total": 1, "hits": []}})(),
    )

    result = knowledge.search_party_knowledge.func(query="三重一大", tool_call_id="call-2")

    assert result.ok is True
    assert result.data["retrievalMode"] == "offline_keyword_fallback"
