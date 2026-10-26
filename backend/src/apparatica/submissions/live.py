"""The events of a submission as Server-Sent Events (ADR-0008, specs/07 §4.2).

Live: the entries of `sub:<id>` after the client's last event id, then new ones from the reader of
the process, until `finalized`. While the check waits, a `queue` event every 2 s carries its
position; it has no `id:` and is not stored. After the stream expired: the journal
`events.jsonl.zst` of the last attempt with the same ids, and `finalized` from the database.
A `: keepalive` comment goes every 15 s.
"""

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog
import zstandard
from botocore.exceptions import BotoCoreError, ClientError

from apparatica.core.storage import Storage
from apparatica.submissions.events import FinalizedEvent, QueueEvent
from apparatica.submissions.queue import JobQueue
from apparatica.submissions.streams import Entry, StreamHub, entry_key
from judge.core.jobs import submission_stream_key
from judge.core.verdict import VerdictDetail

log = structlog.get_logger(__name__)

KEEPALIVE_S = 15.0
QUEUE_EVERY_S = 2.0
KEEPALIVE = b": keepalive\n\n"


@dataclass(frozen=True)
class Watched:
    """What the stream needs of a submission, read before streaming starts."""

    id: uuid.UUID
    status: str
    final: bool
    queue: str  # the queue it waits in
    verdict_detail: dict[str, Any] | None
    finished_at: datetime | None
    journal: str | None  # storage key of the events of its last attempt

    def finalized(self) -> FinalizedEvent:
        return FinalizedEvent(
            status=self.status,  # type: ignore[arg-type]  # a final status
            verdict_detail=VerdictDetail.model_validate(self.verdict_detail or {}),
        )


def sse(event: dict[str, Any], entry_id: str | None = None) -> bytes:
    """One event: `id:` (a stream entry id), `event:` its type, `data:` one line of JSON."""
    head = f"id: {entry_id}\n" if entry_id is not None else ""
    data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"{head}event: {event.get('type', 'message')}\ndata: {data}\n\n".encode()


def _after(entry_id: str) -> str:
    ms, seq = entry_key(entry_id)
    return f"{ms}-{seq + 1}"


async def live_events(
    watched: Watched,
    after: str,
    hub: StreamHub,
    job_queue: JobQueue,
) -> AsyncIterator[bytes]:
    key = submission_stream_key(watched.id)
    last = after
    for entry_id, raw in await hub.history(key, after):
        event = json.loads(raw)
        yield sse(event, entry_id)
        last = entry_id
        if event.get("type") == "finalized":
            return
    if watched.final:  # the stream lost its `finalized`: the database has it
        yield sse(watched.finalized().model_dump(mode="json"), _after(last))
        return

    waiting = watched.status == "queued" and last == after  # no event of a worker yet
    async with hub.subscribe(key, last) as subscription:
        next_keepalive = time.monotonic() + KEEPALIVE_S
        next_queue = time.monotonic()
        while True:
            now = time.monotonic()
            if waiting and now >= next_queue:
                position = await job_queue.position(watched.queue, watched.id)
                if position is None:  # a worker took it
                    waiting = False
                else:
                    yield sse(QueueEvent(position=position).model_dump(mode="json"))
                    next_queue = now + QUEUE_EVERY_S
            if now >= next_keepalive:
                yield KEEPALIVE
                next_keepalive = now + KEEPALIVE_S
            deadline = min(next_keepalive, next_queue) if waiting else next_keepalive
            try:
                entry: Entry = await asyncio.wait_for(
                    subscription.entries.get(), max(0.0, deadline - time.monotonic())
                )
            except TimeoutError:
                continue
            entry_id, raw = entry
            event = json.loads(raw)
            waiting = False
            yield sse(event, entry_id)
            next_keepalive = time.monotonic() + KEEPALIVE_S
            if event.get("type") == "finalized":
                return


async def archived_events(
    watched: Watched, after: str, storage: Storage, bucket: str
) -> AsyncIterator[bytes]:
    last = after
    for entry_id, event in await _journal(watched, storage, bucket):
        if entry_key(entry_id) > entry_key(after):
            yield sse(event, entry_id)
            last = entry_id
    # After every event of the journal and after the client's id; at the finish time if later.
    final_id = _after(last)
    if watched.finished_at is not None:
        finished = f"{int(watched.finished_at.timestamp() * 1000)}-0"
        if entry_key(finished) > entry_key(final_id):
            final_id = finished
    yield sse(watched.finalized().model_dump(mode="json"), final_id)


async def _journal(
    watched: Watched, storage: Storage, bucket: str
) -> list[tuple[str, dict[str, Any]]]:
    """The events of the journal; none when it expired or cannot be read."""
    if watched.journal is None:
        return []
    try:
        data = await asyncio.to_thread(storage.get, bucket, watched.journal)
        text = zstandard.ZstdDecompressor().decompressobj().decompress(data)
    except (BotoCoreError, ClientError, zstandard.ZstdError) as error:
        log.warning("event journal unavailable", key=watched.journal, error=str(error))
        return []
    events = []
    for line in text.splitlines():
        record = json.loads(line)
        if record.get("id") is not None:  # an event the stream never got has no id
            events.append((record["id"], record["event"]))
    return events
