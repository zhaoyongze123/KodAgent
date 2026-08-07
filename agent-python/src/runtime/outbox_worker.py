"""Process entry point for publishing Python runtime outbox facts.

The LangGraph API owns operation transactions, while this worker owns the
network delivery side of the runtime outbox.  Keeping the publisher in a
separate process means a Java outage cannot hold an operation transaction open
and a worker restart can safely reclaim expired leases.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import threading
from collections.abc import Sequence

from ..persistence.operation_store import OperationStore
from .outbox_publisher import RuntimeOutboxPublisher


LOGGER = logging.getLogger("kodagent.runtime.outbox")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish Python runtime outbox facts to Java.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="claim and publish one batch, then exit",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=_env_int("OA_AGENT_RUNTIME_OUTBOX_BATCH_SIZE", 50),
    )
    parser.add_argument(
        "--lease-seconds",
        type=int,
        default=_env_int("OA_AGENT_RUNTIME_OUTBOX_LEASE_SECONDS", 30),
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=_env_int("OA_AGENT_RUNTIME_OUTBOX_MAX_ATTEMPTS", 10),
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=_env_float("OA_AGENT_RUNTIME_OUTBOX_POLL_SECONDS", 2.0),
    )
    parser.add_argument(
        "--retry-base-seconds",
        type=float,
        default=_env_float("OA_AGENT_RUNTIME_OUTBOX_RETRY_BASE_SECONDS", 2.0),
    )
    parser.add_argument(
        "--retry-max-seconds",
        type=float,
        default=_env_float("OA_AGENT_RUNTIME_OUTBOX_RETRY_MAX_SECONDS", 300.0),
    )
    parser.add_argument("--worker-id", default=os.getenv("OA_AGENT_RUNTIME_OUTBOX_WORKER_ID"))
    return parser


def _install_signal_handlers(stop_event: threading.Event) -> None:
    def request_stop(signum: int, _frame: object) -> None:
        LOGGER.info("received signal %s; stopping runtime outbox worker", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)


def _publish_once(publisher: RuntimeOutboxPublisher) -> int:
    result = publisher.publish_once()
    LOGGER.info(
        "runtime outbox batch claimed=%d published=%d failed=%d",
        result.claimed,
        result.published,
        result.failed,
    )
    return 0


def _run_forever(
    publisher: RuntimeOutboxPublisher,
    *,
    stop_event: threading.Event,
    poll_seconds: float,
) -> int:
    poll_seconds = max(0.1, poll_seconds)
    database_backoff = poll_seconds
    while not stop_event.is_set():
        try:
            result = publisher.publish_once()
            LOGGER.info(
                "runtime outbox batch claimed=%d published=%d failed=%d",
                result.claimed,
                result.published,
                result.failed,
            )
            database_backoff = poll_seconds
            # A full batch may have more work waiting.  Yield briefly and
            # immediately poll again; an empty batch uses the normal interval.
            wait_seconds = 0.1 if result.claimed >= publisher.batch_size else poll_seconds
        except Exception:
            # Database outages must not terminate the delivery process.  The
            # next iteration retries with bounded exponential backoff, while
            # the operation transaction remains independent of this worker.
            LOGGER.exception(
                "runtime outbox poll failed; retrying in %.1fs",
                database_backoff,
            )
            wait_seconds = database_backoff
            database_backoff = min(poll_seconds * 16, database_backoff * 2)
        stop_event.wait(wait_seconds)
    return 0


def run_worker(args: argparse.Namespace) -> int:
    if args.batch_size < 1:
        raise ValueError("--batch-size must be at least 1")
    if args.lease_seconds < 1:
        raise ValueError("--lease-seconds must be at least 1")
    if args.max_attempts < 1:
        raise ValueError("--max-attempts must be at least 1")
    if args.poll_seconds <= 0:
        raise ValueError("--poll-seconds must be greater than 0")

    stop_event = threading.Event()
    _install_signal_handlers(stop_event)
    store = OperationStore()
    publisher = RuntimeOutboxPublisher(
        store,
        worker_id=args.worker_id,
        batch_size=args.batch_size,
        lease_seconds=args.lease_seconds,
        max_attempts=args.max_attempts,
        retry_base_seconds=args.retry_base_seconds,
        retry_max_seconds=args.retry_max_seconds,
    )
    LOGGER.info(
        "runtime outbox worker started worker_id=%s batch_size=%d",
        publisher.worker_id,
        publisher.batch_size,
    )
    try:
        if args.once:
            return _publish_once(publisher)
        return _run_forever(
            publisher,
            stop_event=stop_event,
            poll_seconds=args.poll_seconds,
        )
    finally:
        store.close()
        LOGGER.info("runtime outbox worker stopped")


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=os.getenv("OA_AGENT_RUNTIME_OUTBOX_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        return run_worker(_parser().parse_args(argv))
    except Exception:
        LOGGER.exception("runtime outbox worker failed to start")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "run_worker"]
