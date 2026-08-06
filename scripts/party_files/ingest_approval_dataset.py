"""Normalize the approval-policy dataset for knowledge ingestion.

The output is JSONL and contains derived text/rules only; OA permissions are
still rechecked by the Java facade when the data is queried.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def ingest(root: Path, output: Path) -> dict[str, int]:
    output.mkdir(parents=True, exist_ok=True)
    documents = []
    chunks = []
    facts = []
    for rules_path in sorted((root / "policies").glob("*/policy-*.rules.json")):
        rules = json.loads(rules_path.read_text(encoding="utf-8"))
        doc_id = rules["documentId"]
        text_path = rules_path.with_suffix("").with_suffix(".md")
        text = text_path.read_text(encoding="utf-8") if text_path.exists() else ""
        documents.append({"docId": doc_id, "title": rules.get("title"), "docType": rules.get("documentType"), "version": rules.get("version"), "status": rules.get("status"), "origin": "approval_test_dataset"})
        chunks.append({"docId": doc_id, "section": "全文", "ordinal": 0, "content": text})
        for rule in rules.get("rules", []):
            facts.append({"docId": doc_id, "factType": "REQUIREMENT", "ruleId": rule.get("ruleId"), "subject": rule.get("subject"), "condition": rule.get("conditions"), "requiredMaterial": rule.get("requiredAttachments", []), "responsibleParty": rule.get("requiredApprovalNodes", []), "citationText": rule.get("citationText"), "sourceArticle": rule.get("article")})
        (output / f"{doc_id}.rules.json").write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "documents.jsonl").write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in documents) + "\n", encoding="utf-8")
    (output / "chunks.jsonl").write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in chunks) + "\n", encoding="utf-8")
    (output / "facts.jsonl").write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in facts) + "\n", encoding="utf-8")
    return {"documents": len(documents), "chunks": len(chunks), "facts": len(facts)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(ingest(args.root, args.output), ensure_ascii=False))
