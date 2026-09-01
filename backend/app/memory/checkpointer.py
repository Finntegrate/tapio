"""Checkpointer for conversation memory."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


@asynccontextmanager
async def get_checkpointer() -> AsyncIterator[BaseCheckpointSaver]:
    """Yield a checkpointer, held open for the caller's lifetime.

    Postgres by default. Set USE_MEMORY_SAVER=1 for an in-memory store that is
    wiped on restart — local development only, and not safe across workers.

    Yields:
        A checkpointer ready to pass to build_graph
    """
    if os.getenv("USE_MEMORY_SAVER") == "1":
        yield MemorySaver()
        return

    async with AsyncPostgresSaver.from_conn_string(os.environ["DATABASE_URL"]) as saver:
        await saver.setup()
        yield saver
