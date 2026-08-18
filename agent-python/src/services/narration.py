"""Canonical user-visible process narration publisher.

The browser must never have to infer a process row from LangGraph tool-call
chunks.  A narration is persisted first, receives Java's durable cursor, and
only then is written to the LangGraph custom stream.
"""

from collections.abc import Callable
from typing import Any


class NarrationPublisher:
    """Publish one canonical ``narration.upsert`` event.

    ``persist`` is injected to keep the publisher independent from tool
    implementations and straightforward to test.
    """

    def __init__(self, persist: Callable[..., dict[str, Any]]):
        self._persist = persist

    def publish(self, writer: Any, event: dict[str, Any]) -> dict[str, Any]:
        acknowledgement = self._persist(event, require_persist=True) or {}
        # Java owns the durable order.  Do not expose a locally guessed
        # sequence as a presentation cursor.
        cursor = acknowledgement.get("eventCursor")
        if isinstance(cursor, dict):
            event["eventCursor"] = cursor
        event_id = acknowledgement.get("eventId")
        if event_id:
            event["eventId"] = str(event_id)

        if writer:
            writer({
                "type": "agent_event",
                "event": event,
                "text": str(event.get("text") or ""),
            })
        return event
