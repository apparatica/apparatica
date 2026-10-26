"""Cancellation of checks that wait in the queue (specs/07 §3, FR-JDG-10).

The API publishes a cancel on `judge:cancel`; the worker that runs the check stops it and reports
it. A check that no worker has started would wait for one to be cancelled, so the ingestor ends it
at once. A message lost while the ingestor was down costs only time: the worker that takes the check
finds the key `cancel:<id>` and reports it cancelled without running it.
"""

import asyncio
import contextlib
import uuid
from typing import Any

import redis.asyncio
import structlog

from apparatica.judging.ingest import Ingestor, transient
from apparatica.judging.publish import publish_finalized
from judge.core.jobs import CANCEL_CHANNEL

log = structlog.get_logger(__name__)


class CancelWatcher:
    def __init__(
        self, valkey: redis.asyncio.Redis, ingestor: Ingestor, *, retry_s: float = 1.0
    ) -> None:
        self._valkey = valkey
        self._ingestor = ingestor
        self._retry_s = retry_s

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                pubsub: Any = self._valkey.pubsub(ignore_subscribe_messages=True)
                async with pubsub:
                    await pubsub.subscribe(CANCEL_CHANNEL)
                    while not stop.is_set():
                        message = await pubsub.get_message(timeout=1.0)
                        if message is not None:
                            await self.handle(message["data"])
            except Exception as error:
                if not transient(error):
                    raise
                log.warning("cancel channel unavailable", error=str(error))
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), self._retry_s)

    async def handle(self, data: bytes | str) -> None:
        text = data.decode() if isinstance(data, bytes) else data
        try:
            submission_id = uuid.UUID(text.partition(" ")[0])
        except ValueError:
            log.warning("malformed cancel dropped", data=text[:100])
            return
        event = await self._ingestor.cancel_waiting(submission_id)
        if event is not None:
            await publish_finalized(self._valkey, submission_id, event)
