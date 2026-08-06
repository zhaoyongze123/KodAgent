"""Deterministic recovery for an omitted second-stage action.

The model owns semantic domain selection.  Once a domain has been selected,
this module may repair a missing ``action_id`` only when the user request has
an unambiguous, typed shape that maps to one registered action.  It is not a
global keyword router: it never chooses a capability and it never chooses an
executor or a Java path.

The first production case is ``approval_read``.  A common provider failure is
to emit the domain for a simple list query but omit both the action and the
query envelope.  Repeating the route tool cannot add information, so the
domain-scoped recovery creates the same canonical query intent the model was
expected to emit.  Ambiguous or analysis requests remain explicit and are
never silently converted into a list query.
"""

from __future__ import annotations

import re
from typing import Any, TypedDict


class RecoveredAction(TypedDict, total=False):
    action_id: str
    execution_class: str
    candidate_plan: dict[str, Any]
    query_intent: dict[str, Any]
    reason: str


_ANALYSIS_SIGNALS = re.compile(
    r"分析|洞察|趋势|分布|占比|积压|异常|原因|统计|汇总|报表|看板|画像|建议|为什么"
)
_LIST_SIGNALS = re.compile(
    r"查询|查看|找|查找|搜索|列出|罗列|清单|列表|显示|获取|有哪些|最近|最新|前\s*[0-9一二三四五六七八九十两百千]+\s*(?:条|个|项|笔)?|审批记录"
)
_EXPLICIT_LIST_ACTION = re.compile(
    r"查询|查看|找|查找|搜索|列出|罗列|清单|列表|显示|获取|有哪些"
)
_APPLICATION_SCOPE = re.compile(r"我发起|我的申请|发起的审批|已办(?:审批|流程)|历史审批")
_MY_APPLICATIONS = re.compile(r"我发起|我的申请|发起的审批")
_MY_HISTORY = re.compile(r"已办(?:审批|流程)|历史审批|审批历史")
_AMBIGUOUS_ORDER = re.compile(
    r"先.{0,12}(?:取|拿|截取|选|前)\s*[0-9一二三四五六七八九十两百千]+|"
    r"(?:先|再).{0,12}排序|排序.{0,12}(?:再|然后|之后)"
)
_LIMIT = re.compile(
    r"(?:前|最近|最新|取|拿|返回|列出)?\s*(?P<value>[0-9一二三四五六七八九十两百千]+)\s*(?:条|个|项|笔)"
)


def _chinese_number(value: str) -> int | None:
    """Parse the small Chinese cardinal forms used in list limits."""

    value = str(value or "").strip()
    if not value:
        return None
    if value.isdigit():
        return int(value)
    digits = {"零": 0, "一": 1, "两": 2, "二": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if value in digits:
        return digits[value]
    if value == "十":
        return 10
    if "十" in value:
        left, right = value.split("十", 1)
        tens = digits.get(left, 1) if left else 1
        ones = digits.get(right, 0) if right else 0
        return tens * 10 + ones
    if "百" in value:
        left, right = value.split("百", 1)
        hundreds = digits.get(left, 1) if left else 1
        return hundreds * 100 + (_chinese_number(right) or 0)
    if "千" in value:
        left, right = value.split("千", 1)
        thousands = digits.get(left, 1) if left else 1
        return thousands * 1000 + (_chinese_number(right) or 0)
    return None


def _limit_from_message(message: str) -> int | None:
    match = _LIMIT.search(str(message or ""))
    if not match:
        return None
    value = _chinese_number(match.group("value"))
    # The canonicalizer owns the public 1..50 limit contract.  Do not create
    # an invalid plan here; let the normal clarification path handle it.
    return value if value is not None and 1 <= value <= 50 else value


def _sort_from_message(message: str) -> list[dict[str, str]]:
    text = str(message or "")
    if re.search(r"金额.{0,8}(?:最高|最大|最多|高到低|降序)|(?:最高|最大|最多).{0,8}金额", text):
        return [{"field": "amount", "direction": "DESC"}]
    if re.search(r"金额.{0,8}(?:最低|最小|最少|低到高|升序)|(?:最低|最小|最少).{0,8}金额", text):
        return [{"field": "amount", "direction": "ASC"}]
    if re.search(r"(?:等待|积压|待办).{0,8}(?:最久|最长|天数最多|高到低)", text):
        return [{"field": "pending_days", "direction": "DESC"}]
    if re.search(r"最近|最新|新到旧|时间倒序|按时间降序", text):
        return [{"field": "created_time", "direction": "DESC"}]
    return []


def recover_approval_read_action(message: str) -> RecoveredAction | None:
    """Recover one approval-read action from an unambiguous user shape.

    The caller must already have selected ``approval_read``.  Requests that
    name another approval scope, contain an unresolved order ambiguity, or do
    not state a list/analysis intent return ``None`` and keep the normal
    ACTION_SELECTION clarification.
    """

    text = str(message or "").strip()
    if not text or _APPLICATION_SCOPE.search(text):
        return None
    # A mixed request such as “分析最近三条审批” cannot be represented by
    # the current ANALYZE action (which has no bounded-list fields).  Keep it
    # in action selection/clarification instead of silently dropping the
    # ranking/count semantics and analyzing the whole inbox.
    has_rank_or_limit = bool(_sort_from_message(text) or _limit_from_message(text))
    has_explicit_list_action = bool(_EXPLICIT_LIST_ACTION.search(text))
    if _ANALYSIS_SIGNALS.search(text):
        if has_rank_or_limit or has_explicit_list_action:
            # The current analysis action has no bounded-list fields.  Keep
            # mixed analysis/ranking requests in the action-selection
            # clarification path rather than dropping the user's scope.
            return None
        return {
            "action_id": "approval.read.analyze",
            "execution_class": "metadata_query",
            "candidate_plan": {"action_id": "approval.read.analyze", "operation": "ANALYZE"},
            "reason": "domain-scoped analysis intent",
        }
    sort = _sort_from_message(text)
    if not _LIST_SIGNALS.search(text) and not sort:
        return None

    limit = _limit_from_message(text)
    query: dict[str, Any] = {
        "entity": "pending_approval",
        "operation": "rank" if sort else "list",
    }
    if sort:
        query["sort"] = sort
    if limit is not None:
        query["limit"] = limit
    if _AMBIGUOUS_ORDER.search(text):
        query["ambiguities"] = ["查询执行顺序未明确"]
    return {
        "action_id": "approval.read.pending",
        "execution_class": "metadata_query",
        "candidate_plan": {
            "action_id": "approval.read.pending",
            "operation": "PENDING",
            **({"limit": limit} if limit is not None else {}),
            **({"sort": sort} if sort else {}),
        },
        "query_intent": query,
        "reason": "domain-scoped structured approval list intent",
    }


def recover_approval_process_action(message: str) -> RecoveredAction | None:
    """Correct an overlapping approval domain when the scope is explicit.

    ``approval_read`` is the pending inbox domain, while applications and
    completed history belong to ``approval_process``.  Providers occasionally
    collapse both into the former because the user says only “审批”.  An
    explicit owner/history scope is sufficient to make the correction without
    guessing a process instance or exposing any executor path.
    """

    text = str(message or "").strip()
    # Do not collapse a multi-intent request (especially a withdrawal plus a
    # history query) into one read action. The normal planner must clarify or
    # split it explicitly.
    if re.search(r"撤回|取消|删除|通过|驳回|同时|并且|然后|以及|\s并\s|，并", text):
        return None
    if _MY_APPLICATIONS.search(text):
        return {
            "action_id": "approval.process.applications",
            "execution_class": "approval_query",
            "candidate_plan": {
                "action_id": "approval.process.applications",
                "operation": "APPLICATIONS",
            },
            "reason": "explicit user-owned approval application scope",
        }
    if _MY_HISTORY.search(text):
        return {
            "action_id": "approval.process.history",
            "execution_class": "approval_query",
            "candidate_plan": {
                "action_id": "approval.process.history",
                "operation": "HISTORY",
            },
            "reason": "explicit completed approval history scope",
        }
    return None


__all__ = [
    "RecoveredAction",
    "recover_approval_process_action",
    "recover_approval_read_action",
]
