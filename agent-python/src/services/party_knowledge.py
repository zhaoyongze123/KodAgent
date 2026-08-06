"""Small offline knowledge index used by the party-file evaluation workflow.

The index is intentionally read-only and source-configured. Production OA
retrieval must replace this provider with an authorization-filtered Java
facade; the tool contract and citation shape stay the same.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


class PartyKnowledgeIndex:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._documents: list[dict[str, Any]] = []
        self._chunks: list[dict[str, Any]] = []
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        documents = self.root / "documents.jsonl"
        chunks = self.root / "chunks.jsonl"
        if not documents.exists() or not chunks.exists():
            raise FileNotFoundError("党务文件知识索引不存在，请先运行 ingest_dataset.py")
        self._documents = [json.loads(line) for line in documents.read_text(encoding="utf-8").splitlines() if line.strip()]
        self._chunks = [json.loads(line) for line in chunks.read_text(encoding="utf-8").splitlines() if line.strip()]
        self._loaded = True

    @staticmethod
    def _terms(value: str) -> set[str]:
        return {item for item in re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+", value.lower()) if item.strip()}

    def search(self, query: str, *, top_k: int = 5, origin: str | None = None, doc_type: str | None = None) -> dict[str, Any]:
        self.load()
        terms = self._terms(query)
        doc_map = {item["docId"]: item for item in self._documents}
        ranked = []
        for chunk in self._chunks:
            document = doc_map.get(chunk.get("docId"), {})
            if origin and document.get("origin") != origin:
                continue
            if doc_type and document.get("docType") != doc_type:
                continue
            content = str(chunk.get("content") or "")
            score = sum(content.lower().count(term) for term in terms)
            if score <= 0:
                continue
            ranked.append((score, chunk, document))
        ranked.sort(key=lambda item: (-item[0], item[1].get("ordinal", 0)))
        hits = []
        for score, chunk, document in ranked[: max(1, min(top_k, 20))]:
            hits.append({
                "score": score,
                "document": {key: document.get(key) for key in ("docId", "title", "docType", "status", "origin", "publishDate")},
                "citation": {"documentId": chunk.get("docId"), "chunkId": chunk.get("contentHash"), "section": chunk.get("section"), "ordinal": chunk.get("ordinal")},
                "content": chunk.get("content", ""),
            })
        return {"query": query, "total": len(hits), "hits": hits}


def configured_index() -> PartyKnowledgeIndex:
    root = os.getenv("OA_AGENT_PARTY_KNOWLEDGE_INDEX", "").strip()
    if not root:
        raise FileNotFoundError("未配置 OA_AGENT_PARTY_KNOWLEDGE_INDEX")
    return PartyKnowledgeIndex(root)
