"""Party-file recovery handlers and bounded schema repair."""

from __future__ import annotations

import re
from typing import Any

from ..patterns import (
    DATE_QUERY,
    PARTY_FILE_ATTACHMENT_QUERY,
    PARTY_FILE_EXPLICIT_WRITE,
)
from ...planning.party_file import normalize_party_file_operation


def party_file_attachment_plan(
    message: str,
    candidate_plan: dict[str, Any] | None = None,
    capability_id: str | None = None,
) -> dict[str, Any] | None:
    """Keep attachment inspection on an explicit, typed source boundary.

    The source ID may come from the current compiled plan, but never from
    Redis working memory or an ordinal selected from a previous query. Java
    rechecks visibility and attachment ownership at the read boundary.
    """
    payload = candidate_plan if isinstance(candidate_plan, dict) else {}
    raw_operation = str(payload.get("operation") or payload.get("action") or "").strip().upper().replace("-", "_")
    raw_entity = str(
        payload.get("entity") or payload.get("object_type") or payload.get("objectType")
        or payload.get("domain") or capability_id or ""
    ).strip().lower().replace("-", "_")
    party_file_entity = raw_entity in {"party_file", "party_files", "partyfile", "partyfiles", "party_document"}
    typed_attachment = raw_operation in {
        "ATTACHMENT", "ATTACHMENTS", "ATTACHMENT_QUERY", "ATTACHMENT_DELIVERY",
        "DETAIL_WITH_ATTACHMENTS", "FILE_ATTACHMENTS",
    } and (party_file_entity or bool(re.search(r"党务文件|文件", str(message or ""))))
    text = str(message or "").strip()
    if not typed_attachment and not PARTY_FILE_ATTACHMENT_QUERY.search(text):
        return None
    if not typed_attachment and not re.search(r"党务文件|文件", text):
        return None
    if PARTY_FILE_EXPLICIT_WRITE.search(text) and not re.search(r"核对|查看|预览|下载|有没有|是否包含|可发送", text):
        return None
    source = (
        payload.get("source_party_file_id") or payload.get("sourcePartyFileId")
        or payload.get("file_id") or payload.get("fileId")
    )
    if source is None:
        return {"status": "CLARIFY", "operation": "ATTACHMENTS",
                "message": "请提供要核对附件的党务文件编号。", "options": []}
    try:
        source_id = int(source)
    except (TypeError, ValueError):
        source_id = 0
    if source_id <= 0:
        return {"status": "CLARIFY", "operation": "ATTACHMENTS",
                "message": "请提供有效的党务文件编号。", "options": []}
    return {"status": "RESOLVED", "operation": "ATTACHMENTS", "source_party_file_id": source_id,
            "_authorized_source_fields": ["source_party_file_id"]}


def party_metadata_fallback_plan(message: str) -> dict[str, Any] | None:
    """Recover an explicit structured file query when a provider emits ``{}``."""
    text = str(message or "")
    if "党务文件" not in text or not re.search(r"发布时间|发布日期|发布.*日期", text):
        return None
    match = DATE_QUERY.search(text)
    if not match:
        return None
    target = f"{int(match.group('year')):04d}-{int(match.group('month')):02d}-{int(match.group('day')):02d}"
    mode = "nearest" if re.search(r"最接近|最近|临近", text) else "desc"
    return {
        "capability_id": "party_file",
        "execution_class": "metadata_query",
        "candidate_plan": {
            "action_id": "party_file.metadata",
            "rank": {"field": "publishTime", "mode": mode, "target": target},
            "limit": 20,
            "projection": ["id", "title", "publishTime", "categoryName"],
        },
    }


def recover_party_file_write_candidate(
    message: str,
    candidate_plan: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Recover a party-file write domain from an otherwise typed plan."""
    payload = dict(candidate_plan or {}) if isinstance(candidate_plan, dict) else {}
    for nested_key in ("data", "fields", "document", "content"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            payload = {**nested, **{k: v for k, v in payload.items() if k != nested_key}}
            break
    operation = normalize_party_file_operation(payload.get("operation") or payload.get("action"))
    if operation == "CONFIRM" or payload.get("_confirmation_intent") is True:
        return {**payload, "entity": "party_file", "operation": "CONFIRM", "_confirmation_intent": True}
    entity = str(
        payload.get("entity") or payload.get("object_type") or payload.get("objectType")
        or payload.get("domain") or ""
    ).strip().lower().replace("-", "_")
    source_id = (
        payload.get("source_party_file_id") or payload.get("sourcePartyFileId")
        or payload.get("party_file_id") or payload.get("partyFileId")
    )
    write_fields = (
        "title", "category", "category_name", "categoryName", "category_id", "categoryId",
        "summary", "content", "body", "attachment_file_ids", "attachmentFileIds",
        "publish_time", "publishTime", "targets", "distribution_type", "distributionType",
    )
    has_write_fields = any(payload.get(key) not in (None, "", [], {}) for key in write_fields)
    file_type = str(
        payload.get("file_type") or payload.get("fileType") or payload.get("document_type")
        or payload.get("documentType") or ""
    ).strip().lower()
    if not entity and file_type and (has_write_fields or payload.get("draft_mode") is True):
        entity = "party_file"
    if operation not in {"CREATE", "UPDATE", "DELETE"}:
        if source_id is not None and any(bool(payload.get(key)) for key in ("delete", "remove", "deleteRequested", "removeRequested")):
            operation = "DELETE"
        elif source_id is not None and has_write_fields:
            operation = "UPDATE"
        elif source_id is None and has_write_fields:
            operation = "CREATE"
        else:
            planner_text = str(message or "")
            if entity in {"party_file", "party_files", "partyfile", "partyfiles"} and source_id is not None:
                if re.search(r"删除|移除", planner_text):
                    operation = "DELETE"
                elif re.search(r"更新|修改|编辑", planner_text) and has_write_fields:
                    operation = "UPDATE"
    if operation not in {"CREATE", "UPDATE", "DELETE"}:
        return None
    if entity in {"party_file", "party_files", "partyfile", "partyfiles"}:
        normalized = {**payload, "entity": "party_file", "operation": operation}
        if source_id is not None:
            normalized.setdefault("source_party_file_id", source_id)
        return normalized
    text = str(message or "")
    if "党务文件" not in text:
        return None
    field_markers = (r"标题", r"分类", r"摘要", r"正文", r"内容", r"发文单位", r"分发")
    explicit_field_count = sum(payload.get(key) not in (None, "", [], {}) for key in write_fields)
    if operation == "DELETE" and source_id is not None:
        return {**payload, "entity": "party_file", "operation": operation, "source_party_file_id": source_id}
    explicit_party_file_draft = bool(re.search(r"党务文件", text) and re.search(r"草稿|待确认|不直接发布|正式发布", text))
    if (
        sum(bool(re.search(marker, text)) for marker in field_markers) < 2
        and explicit_field_count < 2
        and not (operation == "CREATE" and has_write_fields and explicit_party_file_draft)
    ):
        return None
    return {**payload, "entity": "party_file", "operation": operation}


def recover_party_file_write_intent(message: str, candidate_plan: dict[str, Any] | None) -> dict[str, Any] | None:
    """Recover a high-confidence party-file write when the plan was dropped."""
    if isinstance(candidate_plan, dict) and any(
        key not in {"execution_class", "executionClass", "plan_class", "planClass"}
        for key in candidate_plan
    ):
        return None
    text = str(message or "").strip()
    if not text or not re.search(r"党务文件", text):
        return None
    explicit_write_request = re.search(
        r"(?:准备|请|帮我|需要|先|直接|我要|请你|把).{0,12}"
        r"(?:起草|创建|新建|拟定|编写|发布|正式发布|生成|修改|更新|编辑|变更|调整|删除|撤销|作废)",
        text,
    )
    if re.search(r"能力|接入|支持|怎么做|如何做|方案|是否|有没有|能不能", text) and not explicit_write_request:
        return None
    create_intent = bool(re.search(r"起草|创建|新建|拟定|编写|生成(?:一份|一个)?(?:待确认)?草稿|正式发布|发布", text))
    update_intent = bool(re.search(r"修改|更新|编辑|变更|调整", text))
    delete_intent = bool(re.search(r"删除|撤销|作废", text))
    if not (create_intent or update_intent or delete_intent):
        return None
    has_document_shape = bool(re.search(r"《[^》]{2,}》", text) or re.search(r"标题|正文|内容|草稿|待确认|不直接发布|发文单位|报送", text))
    if create_intent and not has_document_shape:
        return None
    if delete_intent and not update_intent:
        operation = "DELETE"
    elif update_intent and not create_intent:
        operation = "UPDATE"
    else:
        operation = "CREATE"
    return {"entity": "party_file", "operation": operation, "_route_recovery": "bounded_entity_action_guard"}


__all__ = [
    "party_file_attachment_plan",
    "party_metadata_fallback_plan",
    "recover_party_file_write_candidate",
    "recover_party_file_write_intent",
]
