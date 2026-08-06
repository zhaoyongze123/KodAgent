"""Run the Python Runtime Outbox publisher as a separate process."""

from __future__ import annotations

import signal
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent-python"))

from src.persistence.operation_store import OperationStore, runtime_postgres_dsn
from src.runtime.outbox_publisher import RuntimeOutboxPublisher


def main() -> None:
    stop_event = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())
    store = OperationStore(runtime_postgres_dsn())
    try:
        RuntimeOutboxPublisher(store).run_forever(stop_event=stop_event)
    finally:
        store.close()


if __name__ == "__main__":
    main()
