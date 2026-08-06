"""Generate pgvector embeddings for knowledge chunks and emit SQL updates."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[2] / 'agent-python'))
from src.services.party_embeddings import embed_text, project_embedding


def quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--postgres-uri", default=os.getenv("LANGGRAPH_POSTGRES_URI"))
    parser.add_argument("--tenant-id", type=int, default=None, help="只为指定租户的 READY chunk 生成向量")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.postgres_uri:
        parser.error("必须通过 --postgres-uri 或 LANGGRAPH_POSTGRES_URI 提供 PostgreSQL DSN")
    # Use psql JSON output to avoid a new database driver dependency.
    query = "select coalesce(json_agg(json_build_object('id', c.id, 'content', c.content)), '[]'::json) from knowledge_chunk c join knowledge_document d on d.id = c.document_id where c.status = 'READY' and d.status = 'READY'"
    query += f" and d.tenant_id = {int(args.tenant_id)}" if args.tenant_id is not None else ""
    raw = subprocess.check_output(["psql", args.postgres_uri, "-Atc", query], text=True)
    chunks = json.loads(raw.strip() or "[]")
    statements = ["BEGIN;"]
    for chunk in chunks:
        embedding = embed_text(chunk["content"])
        if not embedding:
            raise SystemExit("embedding provider returned no vector")
        vector = "[" + ",".join(str(value) for value in embedding) + "]"
        projected = "[" + ",".join(str(value) for value in project_embedding(embedding)) + "]"
        statements.append(
            f"UPDATE knowledge_chunk SET embedding = {quote(vector)}::vector, "
            f"embedding_projected = {quote(projected)}::vector WHERE id = {int(chunk['id'])};"
        )
    statements.append("COMMIT;")
    sql = "\n".join(statements) + "\n"
    if args.apply:
        subprocess.run(["psql", args.postgres_uri], input=sql, text=True, check=True)
    else:
        print(sql)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
