from __future__ import annotations

import os
from typing import Annotated

from langchain.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from ..common import ToolResponse, bind_tool_call_id, emit, java_get, java_post, tool_failure, tool_success
from ...services.party_knowledge import configured_index
from ...services.party_embeddings import embed_query, project_embedding


@tool
def search_party_knowledge(query: str, top_k: int = 5, origin: str = "", doc_type: str = "", tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """在已导入的党务文件知识索引中检索，并返回带章节引用的证据。只读。"""
    bind_tool_call_id(tool_call_id)
    if not isinstance(query, str) or not query.strip():
        return tool_failure("PARTY_KNOWLEDGE_QUERY_REQUIRED", "请输入要检索的党务文件问题或关键词。")
    writer = get_stream_writer()
    emit(writer, "tool_started", "📚 正在检索党务文件知识索引……", toolName="search_party_knowledge", toolCallId=tool_call_id)
    try:
        params = {"query": query.strip(), "topK": max(1, min(top_k, 20))}
        embedding = embed_query(query.strip())
        if embedding:
            params["embedding"] = embedding
            params["embeddingProjected"] = project_embedding(embedding)
        if doc_type.strip():
            params["documentType"] = doc_type.strip()
        # Production authorization must remain with Java.  An unscoped local
        # index is only an explicit offline test mode; never use it to hide a
        # Java timeout/401/5xx because that would bypass current OA visibility.
        if os.getenv("OA_AGENT_PARTY_KNOWLEDGE_JAVA", "true").lower() == "true":
            try:
                # A query vector is sent as JSON rather than query parameters;
                # long GET URLs are fragile and lose numeric type information.
                result = java_post("/agent/tools/party-knowledge/search", params) if embedding else java_get("/agent/tools/party-knowledge/search", params)
            except Exception as exc:
                if os.getenv("OA_AGENT_PARTY_KNOWLEDGE_OFFLINE_FALLBACK", "false").lower() != "true":
                    raise RuntimeError("授权知识检索服务不可用") from exc
                result = configured_index().search(query.strip(), top_k=top_k, origin=origin.strip() or None, doc_type=doc_type.strip() or None)
                result["retrievalMode"] = "offline_keyword_fallback"
        else:
            result = configured_index().search(query.strip(), top_k=top_k, origin=origin.strip() or None, doc_type=doc_type.strip() or None)
            result["retrievalMode"] = "offline_keyword"
    except Exception as exc:
        return tool_failure("PARTY_KNOWLEDGE_UNAVAILABLE", "党务文件知识索引暂不可用，请先完成导入或稍后重试。", details=str(exc))
    presentation = {"blockType": "card", "cardType": "party_file_knowledge"}
    emit(writer, "tool_completed", f"✅ 已找到 {result['total']} 条带引用的文件证据", toolName="search_party_knowledge", toolCallId=tool_call_id, result=result, presentation=presentation)
    return tool_success(result, presentation)


@tool
def check_party_knowledge_health(tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """读取真实 OA 授权知识库、pgvector 扩展和向量覆盖率状态。只读。"""
    bind_tool_call_id(tool_call_id)
    try:
        return tool_success(java_get("/agent/tools/party-knowledge/health"), {"blockType": "card", "cardType": "party_file_knowledge_health"})
    except Exception as exc:
        return tool_failure("PARTY_KNOWLEDGE_HEALTH_UNAVAILABLE", "党务知识索引健康状态暂不可用。", details=str(exc))
