"""Runtime helpers for workflow lifecycle events and execution boundaries."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from ..tools.common.events import current_agent_context, emit


class WorkflowRuntime:
    """Emit stable workflow/node lifecycle events.

    Event persistence and stream delivery continue to use the existing event
    envelope.  This helper only standardizes event type and fields so every
    workflow can expose the same audit timeline without coupling the graph to
    the frontend.
    """

    def __init__(self, workflow_type: str, *, version: str = "1", writer: Any = None,
                 emit_fn: Callable[..., dict[str, Any]] = emit,
                 persist_state: bool | None = None) -> None:
        self.workflow_type = workflow_type
        self.version = version
        self.writer = writer
        self._emit = emit_fn
        self.persist_state = writer is not None if persist_state is None else persist_state

    def _event_id(self, phase: str, node: str | None = None) -> str:
        context = current_agent_context()
        identity = json.dumps(
            {
                "runId": context.get("runId"),
                "workflow": self.workflow_type,
                "version": self.version,
                "phase": phase,
                "node": node or "",
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
        value = f"{context.get('runId') or 'local-run'}:workflow:{self.workflow_type}:{phase}:{node or 'root'}:{digest}"
        if len(value) <= 128:
            return value
        # agent_event.event_id is varchar(128) in the Java persistence layer.
        return "wfe:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def _publish(self, event_type: str, text: str, *, status: str,
                 node: str | None = None, **data: Any) -> dict[str, Any]:
        payload = {
            "workflow": self.workflow_type,
            "workflowType": self.workflow_type,
            "workflowVersion": self.version,
            "workflowStatus": status,
            **({"workflowNode": node} if node else {}),
            **data,
        }
        event = self._emit(
            self.writer,
            event_type,
            text,
            eventId=self._event_id(event_type, node),
            **payload,
        )
        return event

    def started(self, text: str = "工作流开始执行", **data: Any) -> dict[str, Any]:
        return self._publish("workflow.started", text, status="started", **data)

    def node_started(self, node: str, text: str = "工作流节点开始执行", **data: Any) -> dict[str, Any]:
        return self._publish("workflow.node.started", text, status="started", node=node, **data)

    def node_completed(self, node: str, text: str = "工作流节点执行完成", **data: Any) -> dict[str, Any]:
        return self._publish("workflow.node.completed", text, status="completed", node=node, **data)

    def blocked(self, node: str | None = None, text: str = "工作流等待继续处理", **data: Any) -> dict[str, Any]:
        return self._publish("workflow.blocked", text, status="blocked", node=node, **data)

    def failed(self, text: str = "工作流执行失败", node: str | None = None, **data: Any) -> dict[str, Any]:
        return self._publish("workflow.failed", text, status="failed", node=node, **data)

    def completed(self, text: str = "工作流执行完成", **data: Any) -> dict[str, Any]:
        return self._publish("workflow.completed", text, status="completed", **data)

    def run(self, fn: Callable[[], Any], *, started_text: str = "工作流开始执行",
            completed_text: str = "工作流执行完成") -> Any:
        self.started(started_text)
        try:
            result = fn()
        except Exception as exc:
            self.failed(str(exc), errorType=type(exc).__name__)
            raise
        self.completed(completed_text)
        return result


__all__ = ["WorkflowRuntime"]
