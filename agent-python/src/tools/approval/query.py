"""Compatibility facade for the split approval Tool modules.

The canonical implementations live in ``templates``, ``requests``,
``history``, ``pending`` and ``actions``.  Keeping this explicit import surface
preserves older route checkpoints and integrations without maintaining a
second implementation.
"""

from .common import (
    approval_failure as _approval_failure,
    approval_read as _approval_read,
    bounded_approval_page as _bounded_approval_page,
    request_payload as _request_payload,
)
from .templates import list_startable_approval_types, preview_approval_request
from .history import (
    get_my_approval_application,
    list_my_approval_applications,
    list_my_approval_history,
)
from .requests import (
    _confirm_approval_request,
    confirm_approval_request_action,
    confirm_approval_withdraw_action,
    create_approval_request_draft,
    create_approval_withdraw_draft,
    create_generic_approval_request_draft,
    submit_approval_request,
)
from .pending import (
    analyze_my_pending_approvals,
    list_my_pending_approvals,
    run_approval_query_plan,
    search_my_pending_approvals,
)
from .actions import (
    _action_approval_task,
    approve_approval_task,
    confirm_approval_batch_action,
    confirm_approval_task_action,
    get_approval_task_detail,
    preview_approval_batch_action,
    preview_approval_task_action,
    reject_approval_task,
)


__all__ = [
    "analyze_my_pending_approvals",
    "approve_approval_task",
    "confirm_approval_batch_action",
    "confirm_approval_request_action",
    "confirm_approval_task_action",
    "confirm_approval_withdraw_action",
    "create_approval_request_draft",
    "create_approval_withdraw_draft",
    "create_generic_approval_request_draft",
    "get_approval_task_detail",
    "get_my_approval_application",
    "list_my_approval_applications",
    "list_my_approval_history",
    "list_my_pending_approvals",
    "list_startable_approval_types",
    "preview_approval_batch_action",
    "preview_approval_request",
    "preview_approval_task_action",
    "reject_approval_task",
    "run_approval_query_plan",
    "search_my_pending_approvals",
    "submit_approval_request",
]
