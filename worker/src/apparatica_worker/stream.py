"""The streams a worker writes to valkey-queue (ADR-0008, ADR-0009, specs/07 §4.1).

`sub:<id>` carries the events of a check to the browser: the pipeline events with the attempt, log
lines glued for ~75 ms or up to 8 KB, a heartbeat once a second while a stage is silent.
`judge:results` carries the results to the ingestor, each record with the job token.
"""

import json
import threading
import time
from collections.abc import Callable
from types import TracebackType
from typing import Any, Self

import redis
import structlog

from judge.core.events import EVENT, Event, HeartbeatEvent, LogEvent, StageEndEvent, StageStartEvent
from judge.core.jobs import (
    RESULTS_STREAM,
    RESULTS_STREAM_FIELD,
    SUBMISSION_STREAM_FIELD,
    SUBMISSION_STREAM_MAXLEN,
    SUBMISSION_STREAM_TTL_S,
    JudgeJob,
    ResultRecord,
    StageEndRecord,
    submission_stream_key,
)

log = structlog.get_logger(__name__)

GLUE_S = 0.075  # log lines of a stage and channel are glued for this long ...
GLUE_BYTES = 8 << 10  # ... or up to this size
HEARTBEAT_S = 1.0  # a running stage that wrote nothing for this long sends a heartbeat


class ValkeyStreamSink:
    """The events of one attempt to `sub:<id>`. `journal` keeps every entry as written, with its
    stream id, for `events.jsonl` (the SSE endpoint replays it after the stream expired).

    `with ValkeyStreamSink(...) as sink:` runs the timer of glued lines and heartbeats; leaving
    the block writes what is still glued. A failed write is logged, not raised: the check goes on,
    and its results go to the ingestor separately."""

    def __init__(
        self,
        client: redis.Redis,
        job: JudgeJob,
        attempt: int,
        *,
        glue_s: float = GLUE_S,
        glue_bytes: int = GLUE_BYTES,
        heartbeat_s: float = HEARTBEAT_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._key = submission_stream_key(job.submission_id)
        self._attempt = attempt
        self._glue_s, self._glue_bytes, self._heartbeat_s = glue_s, glue_bytes, heartbeat_s
        self._clock = clock
        self._lock = threading.Condition()
        self._closed = False
        self._thread = threading.Thread(target=self._tick, daemon=True)
        # The glued lines: the first event, since when, the lines, their size.
        self._glued: tuple[LogEvent, float, list[str], int] | None = None
        self._stage: tuple[str, float] | None = None  # the running stage and its start
        self._written = clock()
        self._failed = False
        self.journal: list[bytes] = []

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        with self._lock:
            self._flush()
            self._closed = True
            self._lock.notify()
        self._thread.join()

    def emit(self, event: Event) -> None:
        with self._lock:
            if isinstance(event, LogEvent):
                self._glue(event)
                return
            self._flush()
            if isinstance(event, StageStartEvent):
                self._stage = (event.stage, self._clock())
            elif isinstance(event, StageEndEvent):
                self._stage = None
            self._write(json.loads(EVENT.dump_json(event)))
            self._lock.notify()  # a stage started or ended: the heartbeat timer changed

    def _glue(self, event: LogEvent) -> None:
        size = len(event.text.encode()) + 1
        if self._glued is not None:
            first, since, lines, glued = self._glued
            if (first.stage, first.ch) == (event.stage, event.ch) and (
                glued + size <= self._glue_bytes
            ):
                lines.append(event.text)
                self._glued = (first, since, lines, glued + size)
                return
            self._flush()
        self._glued = (event, self._clock(), [event.text], size)
        if size >= self._glue_bytes:  # a long line goes at once
            self._flush()
        self._lock.notify()  # the timer now waits for this line

    def _flush(self) -> None:
        if self._glued is None:
            return
        first, _, lines, _ = self._glued
        self._glued = None
        text = "".join(line + "\n" for line in lines)
        self._write({"type": "log", "stage": first.stage, "ch": first.ch, "text": text})

    def _write(self, data: dict[str, Any]) -> None:
        event = data | {"attempt": self._attempt}
        payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        entry_id: str | None = None
        try:
            pipe = self._client.pipeline(transaction=False)
            pipe.xadd(
                self._key,
                {SUBMISSION_STREAM_FIELD: payload},
                maxlen=SUBMISSION_STREAM_MAXLEN,
                approximate=True,
            )
            if not self.journal:
                pipe.expire(self._key, SUBMISSION_STREAM_TTL_S)
            entry_id = pipe.execute()[0].decode()
        except redis.RedisError as error:
            if not self._failed:  # once per attempt: the stream is down, not each event
                log.warning("submission stream unavailable", key=self._key, error=str(error))
            self._failed = True
        self._written = self._clock()
        record = {"id": entry_id, "event": event}
        self.journal.append(json.dumps(record, ensure_ascii=False).encode() + b"\n")

    def _tick(self) -> None:
        with self._lock:
            while not self._closed:
                now = self._clock()
                if self._glued is not None and now - self._glued[1] >= self._glue_s:
                    self._flush()
                if self._stage is not None and now - self._written >= self._heartbeat_s:
                    elapsed = round((now - self._stage[1]) * 1000)
                    heartbeat = HeartbeatEvent(stage=self._stage[0], elapsed_ms=elapsed)
                    self._write(heartbeat.model_dump(mode="json"))
                self._lock.wait(self._next_tick())

    def _next_tick(self) -> float | None:
        deadlines = []
        if self._glued is not None:
            deadlines.append(self._glued[1] + self._glue_s)
        if self._stage is not None:
            deadlines.append(self._written + self._heartbeat_s)
        return max(0.0, min(deadlines) - self._clock()) if deadlines else None


class ResultsStream:
    """Records to `judge:results`. A final record is retried: without it the check waits for the
    watchdog of the ingestor."""

    def __init__(self, client: redis.Redis, *, retries: int = 3, backoff_s: float = 0.5) -> None:
        self._client = client
        self._retries, self._backoff_s = retries, backoff_s

    def write(self, record: ResultRecord, *, final: bool = False) -> bool:
        payload = record.model_dump_json()
        tries = self._retries if final else 1
        for attempt in range(tries):
            try:
                self._client.xadd(RESULTS_STREAM, {RESULTS_STREAM_FIELD: payload})
                return True
            except redis.RedisError as error:
                log.warning(
                    "results stream unavailable",
                    submission_id=str(record.submission_id),
                    record=record.type,
                    error=str(error),
                )
                if attempt + 1 < tries:
                    time.sleep(self._backoff_s * 2**attempt)
        log.error("result lost", submission_id=str(record.submission_id), record=record.type)
        return False


class ResultsSink:
    """Sends each stage result to the ingestor as the stage ends (partial results)."""

    def __init__(self, results: ResultsStream, job: JudgeJob, attempt: int) -> None:
        self._results, self._job, self._attempt = results, job, attempt

    def emit(self, event: Event) -> None:
        if isinstance(event, StageEndEvent):
            self._results.write(
                StageEndRecord(
                    submission_id=self._job.submission_id,
                    attempt=self._attempt,
                    token=self._job.token,
                    result=event.result,
                )
            )
