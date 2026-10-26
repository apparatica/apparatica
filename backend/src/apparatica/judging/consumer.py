"""The ingestor process: reads `judge:results` through a consumer group (ADR-0009).

An entry is acknowledged and deleted after its record was applied or dropped. A failure of the
database or of Valkey leaves it pending: the consumer reads its own pending entries before new
ones, and takes over the entries that another consumer left idle (it died). After a record ended
a check, `finalized` goes to the submission stream, whose TTL is then shortened.
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
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError

from apparatica.core.db import Database
from apparatica.core.settings import Settings
from apparatica.judging.ingest import Ingestor, InvalidRecordError
from apparatica.judging.retention import load_retention
from apparatica.submissions.events import FinalizedEvent
from apparatica.submissions.tokens import JobTokens
from judge.core.jobs import (
    RESULT_RECORD,
    RESULTS_STREAM,
    RESULTS_STREAM_FIELD,
    SUBMISSION_STREAM_FIELD,
    SUBMISSION_STREAM_FINAL_TTL_S,
    SUBMISSION_STREAM_MAXLEN,
    submission_stream_key,
)

log = structlog.get_logger(__name__)

GROUP = "ingest"
Entry = tuple[bytes, dict[bytes, bytes] | None]  # a deleted entry still pending has no fields


def transient(error: BaseException) -> bool:
    """The database or Valkey is unreachable: the entry is retried, not dropped."""
    if isinstance(error, DBAPIError):
        return isinstance(error, OperationalError | InterfaceError) or error.connection_invalidated
    return isinstance(error, OSError | RedisConnectionError | RedisTimeoutError)


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
                await self._publish(record.submission_id, finalized)
        await self._ack(entry_id)

    async def _publish(self, submission_id: Any, event: FinalizedEvent) -> None:
        key = submission_stream_key(submission_id)
        async with self._valkey.pipeline(transaction=False) as pipe:
            pipe.xadd(
                key,
                {SUBMISSION_STREAM_FIELD: event.model_dump_json()},
                maxlen=SUBMISSION_STREAM_MAXLEN,
                approximate=True,
            )
            pipe.expire(key, SUBMISSION_STREAM_FINAL_TTL_S)
            await pipe.execute()

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
    database = Database(settings.database_url)
    valkey = redis.asyncio.Redis.from_url(
        settings.queue_url, socket_timeout=10, socket_connect_timeout=5
    )
    name = settings.ingest_consumer or f"{socket.gethostname()}:{os.getpid()}"
    try:
        await ResultsConsumer(valkey, Ingestor(database, tokens, retention), name).run(stop)
    finally:
        await valkey.aclose()
        await database.dispose()
