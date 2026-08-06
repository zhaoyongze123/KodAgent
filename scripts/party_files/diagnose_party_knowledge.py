#!/usr/bin/env python3
"""Read-only readiness check for party-file pgvector retrieval.

It deliberately does not print connection strings, document contents, vectors,
or credentials. Use it before enabling OA_AGENT_KNOWLEDGE_EMBEDDING=true.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys


def scalar(uri: str, statement: str) -> str:
    return subprocess.check_output(["psql", uri, "-At", "-v", "ON_ERROR_STOP=1", "-c", statement], text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Check party knowledge vector retrieval readiness")
    parser.add_argument("--postgres-uri", default=os.getenv("LANGGRAPH_POSTGRES_URI"))
    args = parser.parse_args()
    if not args.postgres_uri:
        parser.error("必须通过 --postgres-uri 或 LANGGRAPH_POSTGRES_URI 提供 PostgreSQL DSN")
    try:
        extension = scalar(args.postgres_uri, "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')") == "t"
        dimensions = scalar(args.postgres_uri, """
            SELECT coalesce(string_agg(attname || ':' || format_type(atttypid, atttypmod), ',' ORDER BY attname), '')
            FROM pg_attribute
            WHERE attrelid = 'knowledge_chunk'::regclass
              AND attname IN ('embedding', 'embedding_projected') AND NOT attisdropped
        """)
        counts = scalar(args.postgres_uri, """
            SELECT count(*) || ',' || count(embedding) || ',' || count(embedding_projected)
            FROM knowledge_chunk
        """)
        index = scalar(args.postgres_uri, """
            SELECT EXISTS (
              SELECT 1 FROM pg_indexes WHERE schemaname = current_schema()
              AND tablename = 'knowledge_chunk' AND indexname = 'idx_knowledge_chunk_embedding_projected'
              AND indexdef ILIKE '%USING hnsw%'
            )
        """) == "t"
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(json.dumps({"ready": False, "reason": "postgres_unavailable", "detail": exc.__class__.__name__}, ensure_ascii=False))
        return 2

    total, full, projected = (int(item) for item in counts.split(","))
    expected_dimensions = dimensions == "embedding:vector(4096),embedding_projected:vector(1536)"
    ready = extension and expected_dimensions and index and (total == 0 or (total == full == projected))
    print(json.dumps({
        "ready": ready,
        "pgvector": extension,
        "columnTypes": dimensions,
        "chunkCount": total,
        "fullEmbeddingCount": full,
        "projectedEmbeddingCount": projected,
        "hnswProjectedIndex": index,
        "nextAction": None if ready else "run party_knowledge_vector.sql, then embed_party_knowledge.py --apply",
    }, ensure_ascii=False))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
