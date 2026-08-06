"""Emit idempotent SQL for loading the synthetic approval policy index.

The generated source IDs are in the reserved 900000 range and must never be
used as real OA party-file IDs. Production imports must replace them with
IDs returned by the authorized OA file ingestion job.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def quote(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return "'" + str(value).replace("'", "''") + "'"


def emit(root: Path, tenant_id: int = 1) -> None:
    print("BEGIN;")
    for path in sorted((root / "policies").glob("*/policy-*.rules.json")):
        rules = json.loads(path.read_text(encoding="utf-8"))
        policy_no = int(str(rules["documentId"]).split("-")[-1])
        document_id = 900000 + policy_no
        source_id = document_id
        text_path = path.with_suffix("").with_suffix(".md")
        text = text_path.read_text(encoding="utf-8") if text_path.exists() else ""
        content_hash = f"approval-dataset-{rules['documentId']}"
        print(f"INSERT INTO knowledge_document (id, tenant_id, source_party_file_id, title, document_type, content_hash, status, published_at) VALUES ({document_id}, {tenant_id}, {source_id}, {quote(rules.get('title'))}, {quote(rules.get('documentType') or '制度')}, {quote(content_hash)}, 'READY', {quote(rules.get('publishDate'))}) ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title, document_type=EXCLUDED.document_type, content_hash=EXCLUDED.content_hash, status='READY';")
        chunk_id = 910000 + policy_no
        print(f"INSERT INTO knowledge_chunk (id, document_id, section, ordinal, content, content_hash, search_vector, status) VALUES ({chunk_id}, {document_id}, '全文', 0, {quote(text)}, {quote(content_hash)}, to_tsvector('simple', {quote(text)}), 'READY') ON CONFLICT (id) DO UPDATE SET content=EXCLUDED.content, content_hash=EXCLUDED.content_hash, search_vector=EXCLUDED.search_vector, status='READY';")
        for index, rule in enumerate(rules.get("rules", []), 1):
            fact_id = document_id * 100 + index
            print("INSERT INTO knowledge_fact (id, document_id, chunk_id, fact_type, subject, action, responsible_party, condition, required_material, fact_key, fact_value, confidence, status) VALUES ("
                  f"{fact_id}, {document_id}, {chunk_id}, 'REQUIREMENT', {quote(rule.get('subject'))}, {quote('审批校验')}, {quote(rule.get('requiredApprovalNodes', []))}, {quote(rule.get('conditions', []))}, {quote(rule.get('requiredAttachments', []))}, {quote(rule.get('ruleId'))}, {quote(rule.get('citationText'))}, 1.0, 'READY') ON CONFLICT (id) DO UPDATE SET fact_value=EXCLUDED.fact_value, condition=EXCLUDED.condition, required_material=EXCLUDED.required_material, status='READY';")
    print("COMMIT;")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--tenant-id", type=int, default=1)
    args = parser.parse_args()
    emit(args.root, args.tenant_id)
