"""The streams of a worker (specs/07 §4.1, ADR-0009): events of a check in `sub:<id>`, glued and
with heartbeats; results with the job token in `judge:results`."""

import json
import time
import uuid
from typing import Any

import pytest
import redis
from stream_helpers import read_stream

from apparatica_worker.report import AttemptReport, StreamReporter
from apparatica_worker.stream import ResultsSink, ResultsStream, ValkeyStreamSink
from judge.core.events import (
    DoneEvent,
    LogEvent,
    StageEndEvent,
    StageStartEvent,
    TruncatedEvent,
)
from judge.core.jobs import (
    RESULT_RECORD,
    RESULTS_STREAM,
    AttemptFailedRecord,
    DoneRecord,
    JudgeJob,
    StageEndRecord,
    StoredArtifact,
    submission_stream_key,
)
from judge.core.stage import StageResult

JOB = JudgeJob(
    submission_id=uuid.uuid4(),
    token="v1.job-token",
    problem="mux4",
    version=1,
    package_uri="mux4/1.tar.zst",
    content_hash="abc",
    resource_class="light",
    kind="run",
    seed=1,
    code="module mux4; endmodule\n",
    toolchain_profile="sv-dev",
    toolchain_image="apparatica-toolchain:dev",
)
RESULT = StageResult(key="lint", type="lint", ordinal=1, status="passed", metrics_schema="lint/v1")


def events(client: redis.Redis) -> list[dict[str, Any]]:
    return [event for _, event in read_stream(client, submission_stream_key(JOB.submission_id))]


def test_the_events_of_an_attempt(valkey_url: str) -> None:
    client = redis.Redis.from_url(valkey_url)
    with ValkeyStreamSink(client, JOB, 2, glue_s=10) as sink:
        sink.emit(StageStartEvent(stage="lint", stage_type="lint", ordinal=1))
        for text in ("a", "b", "c"):
            sink.emit(LogEvent(stage="lint", ch="out", text=text))
        sink.emit(LogEvent(stage="lint", ch="err", text="%Error: x"))  # another channel
        sink.emit(TruncatedEvent(stage="lint", limit_kb=16))
        sink.emit(StageEndEvent(result=RESULT))
        sink.emit(DoneEvent())
    written = events(client)
    assert [(e["type"], e.get("text")) for e in written] == [
        ("stage_start", None),
        ("log", "a\nb\nc\n"),  # whole lines, glued
        ("log", "%Error: x\n"),
        ("truncated", None),
        ("stage_end", None),
        ("done", None),
    ]
    assert all(e["attempt"] == 2 for e in written)
    assert written[2]["ch"] == "err"
    # The journal of events.jsonl is the stream as written: the SSE endpoint replays it by id.
    journal = [json.loads(line) for line in sink.journal]
    stream = read_stream(client, submission_stream_key(JOB.submission_id))
    assert [(r["id"], r["event"]) for r in journal] == stream
    assert 0 < client.ttl(submission_stream_key(JOB.submission_id)) <= 86400


def test_lines_are_glued_up_to_a_size(valkey_url: str) -> None:
    client = redis.Redis.from_url(valkey_url)
    with ValkeyStreamSink(client, JOB, 1, glue_s=10, glue_bytes=8) as sink:
        for text in ("abc", "def", "ghi", "a-line-longer-than-the-glue"):
            sink.emit(LogEvent(stage="lint", ch="out", text=text))
    assert [e["text"] for e in events(client)] == [
        "abc\ndef\n",
        "ghi\n",
        "a-line-longer-than-the-glue\n",
    ]


def test_glued_lines_wait_for_the_glue_time_only(valkey_url: str) -> None:
    client = redis.Redis.from_url(valkey_url)
    with ValkeyStreamSink(client, JOB, 1, glue_s=0.05) as sink:
        sink.emit(LogEvent(stage="lint", ch="out", text="alone"))
        assert events(client) == []
        deadline = time.monotonic() + 2
        while not events(client) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert [e["text"] for e in events(client)] == ["alone\n"]


def test_a_silent_stage_sends_heartbeats(valkey_url: str) -> None:
    client = redis.Redis.from_url(valkey_url)
    with ValkeyStreamSink(client, JOB, 1, heartbeat_s=0.1) as sink:
        time.sleep(0.25)  # no stage runs: no heartbeat
        sink.emit(StageStartEvent(stage="sim_run", stage_type="sim", ordinal=3))
        time.sleep(0.45)
        sink.emit(StageEndEvent(result=RESULT))
        time.sleep(0.25)  # the stage ended: no heartbeat
    written = events(client)
    assert written[0]["type"] == "stage_start"
    assert written[-1]["type"] == "stage_end"
    beats = written[1:-1]
    assert 3 <= len(beats) <= 5
    assert {(b["type"], b["stage"], b["note"], b["attempt"]) for b in beats} == {
        ("heartbeat", "sim_run", None, 1)
    }
    elapsed = [b["elapsed_ms"] for b in beats]
    assert elapsed == sorted(elapsed)
    assert 90 <= elapsed[0] <= 250


def test_a_stream_failure_does_not_stop_the_check() -> None:
    client = redis.Redis(port=1, socket_connect_timeout=0.2)  # nothing listens
    with ValkeyStreamSink(client, JOB, 1) as sink:
        sink.emit(StageStartEvent(stage="lint", stage_type="lint", ordinal=1))
        sink.emit(DoneEvent())
    assert [json.loads(line)["id"] for line in sink.journal] == [None, None]
    assert not ResultsStream(client, retries=2, backoff_s=0).write(
        AttemptFailedRecord(submission_id=JOB.submission_id, attempt=1, token="t", error_code="X"),
        final=True,
    )


def test_results_carry_the_job_token(valkey_url: str) -> None:
    client = redis.Redis.from_url(valkey_url)
    results = ResultsStream(client)
    ResultsSink(results, JOB, 1).emit(StageEndEvent(result=RESULT))
    ResultsSink(results, JOB, 1).emit(DoneEvent())  # not a result
    log = StoredArtifact(kind="log", stage="lint", key="k", size_bytes=1, sha256="0" * 64)
    reporter = StreamReporter(results)
    reporter.report(AttemptReport(JOB, 1, (RESULT,), (log,)))
    reporter.report(AttemptReport(JOB, 3, error_code="ATTEMPTS_EXHAUSTED"))
    records = [RESULT_RECORD.validate_python(r) for _, r in read_stream(client, RESULTS_STREAM)]
    common: dict[str, Any] = {"submission_id": JOB.submission_id, "token": JOB.token}
    assert records == [
        StageEndRecord(**common, attempt=1, result=RESULT),
        DoneRecord(**common, attempt=1, results=(RESULT,), artifacts=(log,)),
        AttemptFailedRecord(**common, attempt=3, error_code="ATTEMPTS_EXHAUSTED"),
    ]


@pytest.mark.parametrize("record", ["stage_end", "done", "attempt_failed"])
def test_a_record_is_checked(record: str) -> None:
    with pytest.raises(ValueError, match="token"):
        RESULT_RECORD.validate_python(
            {"type": record, "submission_id": str(JOB.submission_id), "attempt": 1}
        )
