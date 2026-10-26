"""One reader of submission streams per API process (ADR-0008, specs/07 §4.2).

The reader makes one `XREAD BLOCK` over every stream that has subscribers and hands the entries to
them in memory: no Valkey connection per client. A subscriber starts after an entry id; the cursor
of a stream goes back to the earliest subscriber, and each subscriber skips what it already has.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import redis.asyncio
import structlog
from redis.exceptions import RedisError

from judge.core.jobs import SUBMISSION_STREAM_FIELD

log = structlog.get_logger(__name__)

Entry = tuple[str, bytes]  # stream entry id, the JSON event


def entry_key(entry_id: str) -> tuple[int, int]:
    """Stream ids compare as (milliseconds, sequence)."""
    ms, _, seq = entry_id.partition("-")
    return int(ms), int(seq or 0)


@dataclass(eq=False)
class Subscription:
    last: str  # the id of the last entry the subscriber has
    entries: asyncio.Queue[Entry] = field(default_factory=asyncio.Queue)

    def offer(self, entry: Entry) -> None:
        if entry_key(entry[0]) > entry_key(self.last):
            self.last = entry[0]
            self.entries.put_nowait(entry)


class StreamHub:
    def __init__(
        self, valkey: redis.asyncio.Redis, *, block_ms: int = 500, count: int = 500
    ) -> None:
        self._valkey = valkey
        self._block_ms, self._count = block_ms, count
        self._subscribers: dict[str, set[Subscription]] = {}
        self._cursors: dict[str, str] = {}
        self._wake = asyncio.Event()
        self._reader: asyncio.Task[None] | None = None

    async def history(self, key: str, after: str) -> list[Entry]:
        """The entries after `after`, up to the end of the stream now."""
        response: Any = await self._valkey.xrange(key, min=f"({after}", count=None)
        return [_entry(entry_id, fields) for entry_id, fields in response]

    async def exists(self, key: str) -> bool:
        return bool(await self._valkey.exists(key))

    @contextlib.asynccontextmanager
    async def subscribe(self, key: str, after: str) -> AsyncIterator[Subscription]:
        subscription = Subscription(after)
        self._subscribers.setdefault(key, set()).add(subscription)
        cursor = self._cursors.get(key)
        if cursor is None or entry_key(after) < entry_key(cursor):
            self._cursors[key] = after
        if self._reader is None or self._reader.done():
            self._reader = asyncio.create_task(self._read())
        self._wake.set()
        try:
            yield subscription
        finally:
            subscribers = self._subscribers.get(key, set())
            subscribers.discard(subscription)
            if not subscribers:
                self._subscribers.pop(key, None)
                self._cursors.pop(key, None)

    async def close(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader
        await self._valkey.aclose()

    async def _read(self) -> None:
        while True:
            if not self._cursors:
                self._wake.clear()
                await self._wake.wait()
                continue
            streams: dict[Any, Any] = dict(self._cursors)
            try:
                response: Any = await self._valkey.xread(
                    streams, count=self._count, block=self._block_ms
                )
            except RedisError as error:  # subscribers keep waiting; the stream is not lost
                log.warning("submission streams unavailable", error=str(error))
                await asyncio.sleep(1)
                continue
            for raw_key, raw_entries in response or []:
                key = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
                entries = [_entry(entry_id, fields) for entry_id, fields in raw_entries]
                if not entries:
                    continue
                # A subscriber that came meanwhile may have moved the cursor back: keep it.
                if self._cursors.get(key) == streams.get(key):
                    self._cursors[key] = entries[-1][0]
                for subscription in list(self._subscribers.get(key, ())):
                    for entry in entries:
                        subscription.offer(entry)


def _entry(entry_id: bytes | str, fields: dict[bytes, bytes]) -> Entry:
    name = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
    return name, fields.get(SUBMISSION_STREAM_FIELD.encode(), b"{}")
