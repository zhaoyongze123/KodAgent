#!/usr/bin/env python3
"""Build a deterministic, permission-neutral knowledge package from the local test set.

The package is an offline import artifact. Production ingestion must still pass
through the Java party-file authorization boundary before indexing or retrieval.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    paragraphs = []
    for paragraph in root.iter(W_NS + "p"):
        text = "".join(node.text or "" for node in paragraph.iter(W_NS + "t"))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n\n".join(paragraphs)


def normalize(text: str) -> str:
    text = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def metadata(markdown: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for label, key in (("文件类型", "doc_type"), ("发布日期", "publish_date"), ("状态", "status"), ("分类", "category")):
        match = re.search(rf"\*\*{label}\*\*：?([^\n]+)", markdown)
        if match:
            result[key] = match.group(1).strip().strip("[]")
    return result


def chunks(text: str, size: int = 3200, overlap: int = 400) -> list[dict[str, object]]:
    headings = list(re.finditer(r"(?m)^(#{1,6})[ \t]+(.+)$", text))
    sections = []
    if not headings:
        sections = [("", text)]
    else:
        for index, heading in enumerate(headings):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            sections.append((heading.group(2).strip(), text[heading.end():end].strip()))
    output = []
    ordinal = 0
    for section, body in sections:
        if not body:
            continue
        start = 0
        while start < len(body):
            end = min(len(body), start + size)
            content = body[start:end].strip()
            if content:
                output.append({"ordinal": ordinal, "section": section, "content": content, "contentHash": hashlib.sha256(content.encode()).hexdigest()})
                ordinal += 1
            if end >= len(body):
                break
            start = max(start + 1, end - overlap)
    return output


def build(source: Path, output: Path) -> dict[str, object]:
    manifest_path = source / "manifest.csv"
    rows = {}
    with manifest_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rows[row["doc_id"]] = row
    documents, all_chunks = [], []
    mismatches = []
    for markdown_path in sorted(source.glob("doc_*.md")):
        doc_id = markdown_path.stem
        markdown = normalize(markdown_path.read_text(encoding="utf-8"))
        docx_path = source / f"{doc_id}.docx"
        docx = normalize(docx_text(docx_path)) if docx_path.exists() else ""
        # DOCX may omit markdown-only metadata; compare body content after removing metadata.
        md_body = normalize(re.sub(r"^\*\*[^\n]+\*\*.*$", "", markdown, flags=re.MULTILINE))
        if docx and len(docx) < max(100, len(md_body) * 0.25):
            mismatches.append({"docId": doc_id, "reason": "DOCX_CONTENT_SHORTER_THAN_MARKDOWN", "markdownChars": len(md_body), "docxChars": len(docx)})
        row = rows.get(doc_id, {})
        document = {
            "docId": doc_id, "title": row.get("title") or markdown.splitlines()[0].lstrip("# "),
            "sourceUrl": row.get("source_url", ""), "sourceDomain": row.get("source_domain", ""),
            "publishDate": row.get("publish_date", ""), "docType": row.get("doc_type", ""),
            "status": row.get("status", ""), "origin": row.get("origin", ""),
            "contentHash": hashlib.sha256(md_body.encode()).hexdigest(), "charCount": len(md_body),
        }
        documents.append(document)
        for chunk in chunks(md_body):
            all_chunks.append({"docId": doc_id, **chunk})
    output.mkdir(parents=True, exist_ok=True)
    (output / "documents.jsonl").write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in documents) + "\n", encoding="utf-8")
    (output / "chunks.jsonl").write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in all_chunks) + "\n", encoding="utf-8")
    report = {"documents": len(documents), "chunks": len(all_chunks), "mismatches": mismatches}
    (output / "quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
