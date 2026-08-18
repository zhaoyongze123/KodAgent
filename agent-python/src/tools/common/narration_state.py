"""Ephemeral model-to-tool narration correlation state.

Durable replay belongs to the Java event store.  This small local cache only
bridges streaming model chunks to the terminal Tool snapshot in one worker;
it is intentionally isolated from the event envelope and can later be
replaced by a Redis compare-and-set implementation without changing callers.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time


@dataclass
class NarrationEntry:
    revision: int
    text: str
    updated_at: float
    completed: bool = False


_ENTRIES: dict[str, NarrationEntry] = {}
_LOCK = threading.Lock()


def next_revision(entry_id: str, text: str, *, completed: bool, throttled: bool,
                  min_interval_seconds: float, min_new_characters: int,
                  ttl_seconds: float = 86400) -> int | None:
    now = time.monotonic()
    with _LOCK:
        stale_before = now - ttl_seconds
        for key, value in list(_ENTRIES.items()):
            if value.updated_at < stale_before:
                _ENTRIES.pop(key, None)
        current = _ENTRIES.get(entry_id)
        if current is not None and current.completed and not completed:
            return None
        if current is not None and current.text == text and current.completed == completed:
            return None
        if throttled and current is not None:
            elapsed = now - current.updated_at
            growth = len(text) - len(current.text)
            if elapsed < min_interval_seconds and growth < min_new_characters:
                return None
        revision = (current.revision if current is not None else 0) + 1
        _ENTRIES[entry_id] = NarrationEntry(revision, text, now, completed)
        return revision


def current_revision(entry_id: str) -> int:
    with _LOCK:
        current = _ENTRIES.get(entry_id)
        return current.revision if current is not None else 1


__all__ = ["NarrationEntry", "current_revision", "next_revision"]
