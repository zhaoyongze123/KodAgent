"""Infrastructure assembly shared by the OA graph entry point."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.redis import RedisSaver


def build_checkpointer():
    """Build the configured persistence backend for resumable agent runs."""
    backend = os.getenv("OA_AGENT_CHECKPOINTER", "").strip().lower()
    if not backend:
        raise RuntimeError(
            "必须显式配置 OA_AGENT_CHECKPOINTER；生产请使用 postgres 或 redis，"
            "隔离测试可使用 memory"
        )
    if backend == "memory":
        return InMemorySaver()
    if backend == "sqlite":
        from langgraph.checkpoint.sqlite import SqliteSaver

        checkpoint_path = Path(
            os.getenv("OA_AGENT_CHECKPOINT_PATH", ".data/kodagent-checkpoints.sqlite")
        )
        if not checkpoint_path.is_absolute():
            checkpoint_path = Path(__file__).resolve().parents[1] / checkpoint_path
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(checkpoint_path), check_same_thread=False)
        saver = SqliteSaver(connection)
        saver.setup()
        return saver
    if backend == "postgres":
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg import Connection
        from psycopg.rows import dict_row

        dsn = os.getenv("LANGGRAPH_POSTGRES_URI") or os.getenv("POSTGRES_URI")
        if not dsn:
            raise RuntimeError("OA_AGENT_CHECKPOINTER=postgres 时必须配置 LANGGRAPH_POSTGRES_URI")
        connection = Connection.connect(
            dsn,
            autocommit=True,
            prepare_threshold=0,
            row_factory=dict_row,
        )
        saver = PostgresSaver(connection)
        saver.setup()
        return saver
    if backend == "redis":
        redis_url = os.getenv("OA_AGENT_REDIS_URL")
        if not redis_url:
            raise RuntimeError("OA_AGENT_CHECKPOINTER=redis 时必须配置 OA_AGENT_REDIS_URL")
        saver = RedisSaver(redis_url=redis_url)
        saver.setup()
        return saver
    raise ValueError(f"不支持的 OA_AGENT_CHECKPOINTER 后端: {backend}")
