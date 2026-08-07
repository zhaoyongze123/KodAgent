"""Import currently visible OA party files through the authenticated facade."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request


def sql(value: object) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def get(base: str, path: str, params: dict[str, object], headers: dict[str, str]) -> dict:
    url = base.rstrip("/") + path + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def build_sql(base: str, key: str, user_id: str, tenant_id: int, identity_ticket: str = "") -> str:
    headers = {"X-Agent-Key": key, "X-Agent-Permission": "party-file:read", "X-Agent-Tool": "search_party_files"}
    if not identity_ticket.strip():
        raise ValueError("必须通过 --identity-ticket 或 OA_AGENT_IDENTITY_TICKET 提供身份票据")
    headers["X-Agent-Identity"] = identity_ticket.strip()
    files = []
    page_no = 1
    while True:
        page = get(base, "/agent/tools/party-files/my-page", {"pageNo": page_no, "pageSize": 50}, headers)
        batch = page.get("list") or []
        files.extend(batch)
        total = int(page.get("total") or len(files))
        if not batch or len(files) >= total:
            break
        page_no += 1
    statements = ["BEGIN;"]
    for item in files:
        source_id = int(item["id"])
        document_id = 700000 + source_id
        detail = get(base, "/agent/tools/party-files/my-get", {"id": source_id}, {**headers, "X-Agent-Tool": "get_party_file_detail"})
        content = clean(str(detail.get("content") or item.get("content") or ""))
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        title = detail.get("title") or item.get("title") or f"OA党务文件-{source_id}"
        doc_type = detail.get("categoryName") or item.get("categoryName") or "OA党务文件"
        statements.append(f"INSERT INTO knowledge_document (id, tenant_id, source_party_file_id, title, document_type, content_hash, status) VALUES ({document_id}, {tenant_id}, {source_id}, {sql(title)}, {sql(doc_type)}, {sql(digest)}, 'READY') ON CONFLICT (id) DO UPDATE SET tenant_id=EXCLUDED.tenant_id, source_party_file_id=EXCLUDED.source_party_file_id, title=EXCLUDED.title, document_type=EXCLUDED.document_type, content_hash=EXCLUDED.content_hash, status='READY';")
        chunk_id = 710000 + source_id
        statements.append(f"INSERT INTO knowledge_chunk (id, document_id, section, ordinal, content, content_hash, search_vector, status) VALUES ({chunk_id}, {document_id}, '全文', 0, {sql(content)}, {sql(digest)}, to_tsvector('simple', {sql(content)}), 'READY') ON CONFLICT (id) DO UPDATE SET content=EXCLUDED.content, content_hash=EXCLUDED.content_hash, search_vector=EXCLUDED.search_vector, status='READY';")
    statements.append("COMMIT;")
    print(f"visible_files={len(files)}")
    return "\n".join(statements) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("OA_AGENT_BASE_URL", "http://127.0.0.1:48080"))
    parser.add_argument("--api-key", default=os.getenv("OA_AGENT_API_KEY"))
    parser.add_argument("--user-id", default=os.getenv("OA_AGENT_USER_ID", "1"))
    parser.add_argument("--tenant-id", type=int, default=int(os.getenv("OA_AGENT_CONTEXT_TENANT_ID", "1")))
    parser.add_argument("--identity-ticket", default=os.getenv("OA_AGENT_IDENTITY_TICKET", ""))
    parser.add_argument("--postgres-uri", default=os.getenv("LANGGRAPH_POSTGRES_URI"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.api_key:
        parser.error("必须通过 --api-key 或 OA_AGENT_API_KEY 提供 Agent 服务密钥")
    if not args.postgres_uri:
        parser.error("必须通过 --postgres-uri 或 LANGGRAPH_POSTGRES_URI 提供 PostgreSQL DSN")
    statements = build_sql(args.base_url, args.api_key, args.user_id, args.tenant_id, args.identity_ticket)
    if args.apply:
        subprocess.run(["psql", args.postgres_uri], input=statements, text=True, check=True)
    else:
        print(statements)
