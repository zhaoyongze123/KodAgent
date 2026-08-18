from .auth import AGENT_TIMEZONE, _java_request_config
from .events import (
    bind_agent_context,
    bind_tool_call_id,
    current_agent_context,
    emit,
    is_run_paused,
    mark_run_paused,
    mark_run_resumed,
    progress_event_type,
    report_progress,
    set_message_context,
    set_operation_context,
)
from .contracts import (
    TOOL_CONTRACTS,
    ToolError,
    ToolResponse,
    apply_tool_contracts,
    get_tool_contract,
    redact_sensitive,
    tool_failure,
    tool_success,
)
from .executor import invoke_tool
from .presentation import PresentationSpec, normalize_presentation, presentation_for_response
from .http_client import (
    JavaFacadeConnectionError,
    JavaFacadeBusinessError,
    JavaFacadeHttpError,
    JavaFacadeJsonDecodeError,
    JavaFacadeResponseTypeError,
    as_json,
    delete_meeting_draft,
    get_meeting_draft,
    get_meeting_approval,
    get_meeting_booking_commit_status,
    get_party_file_commit_status,
    get_approval_task_action_status,
    reconcile_approval_task_action,
    get_personal_schedule_commit_status,
    java_get,
    java_get_list,
    java_post,
    java_post_list,
    normalize_local_datetime,
    persist_agent_event,
    save_meeting_draft,
    resolve_agent_model,
    update_meeting_draft_status,
)

__all__ = [
    "AGENT_TIMEZONE",
    "JavaFacadeConnectionError",
    "JavaFacadeBusinessError",
    "JavaFacadeHttpError",
    "JavaFacadeJsonDecodeError",
    "JavaFacadeResponseTypeError",
    "TOOL_CONTRACTS",
    "ToolError",
    "ToolResponse",
    "_java_request_config",
    "as_json",
    "apply_tool_contracts",
    "invoke_tool",
    "get_tool_contract",
    "redact_sensitive",
    "delete_meeting_draft",
    "emit",
    "bind_tool_call_id",
    "bind_agent_context",
    "current_agent_context",
    "is_run_paused",
    "mark_run_paused",
    "mark_run_resumed",
    "progress_event_type",
    "set_message_context",
    "set_operation_context",
    "route_conversation",
    "get_meeting_draft",
    "get_meeting_approval",
    "get_meeting_booking_commit_status",
    "get_party_file_commit_status",
    "get_approval_task_action_status",
    "reconcile_approval_task_action",
    "get_personal_schedule_commit_status",
    "java_get",
    "java_get_list",
    "java_post",
    "java_post_list",
    "normalize_local_datetime",
    "persist_agent_event",
    "report_progress",
    "save_meeting_draft",
    "resolve_agent_model",
    "update_meeting_draft_status",
    "tool_failure",
    "tool_success",
    "PresentationSpec",
    "normalize_presentation",
    "presentation_for_response",
]


def __getattr__(name: str):
    """Lazily expose the route tool to avoid an import cycle at startup."""
    if name == "route_conversation":
        from . import conversation

        value = getattr(conversation, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
