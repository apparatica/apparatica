"""The ingestor process: reads `judge:results` through a consumer group (ADR-0009).

An entry is acknowledged and deleted after its record was applied or dropped. A failure of the
database or of Valkey leaves it pending: the consumer reads its own pending entries before new
ones, and takes over the entries that another consumer left idle (it died). After a record ended
a check, `finalized` goes to the submission stream, whose TTL is then shortened.

Next to the consumer, the leading instance runs the periodic tasks (`housekeeping`), and every
instance ends the cancelled checks that wait in the queue (`cancels`).
"""

import asyncio
import contextlib
import os
import socket
from collections.abc import Sequence
from typing import Any

import redis.asyncio
import structlog
from pydantic import ValidationError
from redis.exceptions import ResponseError

from apparatica.core.db import Database
from apparatica.core.settings import Settings
from apparatica.core.storage import Storage
from apparatica.judging.cancels import CancelWatcher
from apparatica.judging.housekeeping import (
    AddressPurge,
    ArtifactPurge,
    GuestPurge,
    Housekeeping,
    Periodic,
    Watchdog,
)
from apparatica.judging.ingest import Ingestor, InvalidRecordError, transient
from apparatica.judging.leader import Leadership
from apparatica.judging.publish import publish_finalized
from apparatica.judging.retention import load_retention
from apparatica.submissions.tokens import JobTokens
from judge.core.jobs import RESULT_RECORD, RESULTS_STREAM, RESULTS_STREAM_FIELD
from judge.core.limits import load_resource_classes

log = structlog.get_logger(__name__)

GROUP = "ingest"
RESOURCE_CLASSES_FILE = "resource-classes.yaml"
WATCHDOG_EVERY_S = 30  # periodic tasks of the leader
PURGE_EVERY_S = 600
Entry = tuple[bytes, dict[bytes, bytes] | None]  # a deleted entry still pending has no fields


class ResultsConsumer:
    def __init__(
        self,
        valkey: redis.asyncio.Redis,
        ingestor: Ingestor,
        name: str,
        *,
        batch: int = 100,
        block_ms: int = 5000,
        claim_idle_ms: int = 60_000,
        retry_s: float = 1.0,
    ) -> None:
        self._valkey = valkey
        self._ingestor = ingestor
        self.name = name
        self._batch, self._block_ms = batch, block_ms
        self._claim_idle_ms, self._retry_s = claim_idle_ms, retry_s

    async def ensure_group(self) -> None:
        """The group reads the stream from its start: results written before it existed count."""
        try:
            await self._valkey.xgroup_create(RESULTS_STREAM, GROUP, id="0", mkstream=True)
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    async def run(self, stop: asyncio.Event) -> None:
        await self.ensure_group()
        log.info("ingest started", consumer=self.name)
        while not stop.is_set():
            try:
                await self.step()
            except Exception as error:
                if not transient(error):
                    raise
                log.warning("ingest paused", error=str(error))
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), self._retry_s)
        log.info("ingest stopped", consumer=self.name)

    async def step(self) -> int:
        """One batch: own pending entries (a failure left them), entries idle at another
        consumer, then new ones. Returns the number of entries handled."""
        entries = await self._read("0", block=None)
        if not entries:
            entries = await self._claim()
        if not entries:
            entries = await self._read(">", block=self._block_ms)
        for entry_id, fields in entries:
            await self._handle(entry_id, fields)
        return len(entries)

    async def _read(self, start: str, block: int | None) -> Sequence[Entry]:
        response: Any = await self._valkey.xreadgroup(
            GROUP, self.name, {RESULTS_STREAM: start}, count=self._batch, block=block
        )
        return response[0][1] if response else []

    async def _claim(self) -> Sequence[Entry]:
        response: Any = await self._valkey.xautoclaim(
            RESULTS_STREAM, GROUP, self.name, self._claim_idle_ms, "0-0", count=self._batch
        )
        claimed: Sequence[Entry] = response[1]
        if claimed:
            log.info("idle results taken over", count=len(claimed))
        return claimed

    async def _handle(self, entry_id: bytes, fields: dict[bytes, bytes] | None) -> None:
        entry = entry_id.decode()
        try:
            record = RESULT_RECORD.validate_json((fields or {})[RESULTS_STREAM_FIELD.encode()])
        except (KeyError, ValidationError) as error:
            log.error("malformed result dropped", entry=entry, error=str(error))
            await self._ack(entry_id)
            return
        try:
            finalized = await self._ingestor.ingest(record)
        except InvalidRecordError as error:
            log.warning(
                "result dropped",
                entry=entry,
                submission_id=str(record.submission_id),
                record=record.type,
                reason=str(error),
            )
        except Exception as error:
            if transient(error):
                raise  # stays pending
            # A record that breaks the ingestor would break it forever: dropped, with the trace.
            log.exception("result failed", entry=entry, submission_id=str(record.submission_id))
        else:
            if finalized is not None:
                await publish_finalized(self._valkey, record.submission_id, finalized)
        await self._ack(entry_id)

    async def _ack(self, entry_id: bytes) -> None:
        async with self._valkey.pipeline(transaction=False) as pipe:
            pipe.xack(RESULTS_STREAM, GROUP, entry_id)
            pipe.xdel(RESULTS_STREAM, entry_id)
            await pipe.execute()


def job_tokens(settings: Settings) -> JobTokens:
    """The key of the API: without it no token can be checked."""
    if settings.job_token_key is None:
        raise RuntimeError("APX_JOB_TOKEN_KEY is required by the ingestor: the key of the API")
    key = settings.job_token_key.get_secret_value().encode()
    return JobTokens(key, ttl_s=settings.job_token_ttl_s)


async def run_ingest(settings: Settings, stop: asyncio.Event) -> None:
    if settings.queue_url is None:
        raise RuntimeError("APX_QUEUE_URL is required by the ingestor")
    tokens = job_tokens(settings)
    retention = load_retention(settings.config_dir)
    classes = load_resource_classes(settings.config_dir / RESOURCE_CLASSES_FILE)
    database = Database(settings.database_url)
    valkey = redis.asyncio.Redis.from_url(
        settings.queue_url, socket_timeout=10, socket_connect_timeout=5
    )
    name = settings.ingest_consumer or f"{socket.gethostname()}:{os.getpid()}"
    watchdog = Watchdog(database, valkey, classes, settings.watchdog_grace_s)
    storage, bucket = Storage(settings), settings.s3_bucket_artifacts
    tasks = [
        Periodic("watchdog", WATCHDOG_EVERY_S, watchdog),
        Periodic("retention", PURGE_EVERY_S, ArtifactPurge(database, storage, bucket)),
        Periodic("addresses", PURGE_EVERY_S, AddressPurge(database, retention.client_ip_hash_days)),
    ]
    if retention.guest_submissions_days is not None:
        guests = GuestPurge(database, storage, bucket, retention.guest_submissions_days)
        tasks.append(Periodic("guests", PURGE_EVERY_S, guests))
    ingestor = Ingestor(database, tokens, retention)
    consumer = ResultsConsumer(valkey, ingestor, name)
    housekeeping = Housekeeping(Leadership(valkey, name), tasks)
    try:
        async with asyncio.TaskGroup() as group:  # a failure of one stops the other
            group.create_task(consumer.run(stop))
            group.create_task(housekeeping.run(stop))
            group.create_task(CancelWatcher(valkey, ingestor).run(stop))
    finally:
        await valkey.aclose()
        await database.dispose()
