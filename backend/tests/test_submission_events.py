"""`GET /submissions/{id}/events` (specs/07 §4.2, FR-CON-05/06): the live stream through the reader
of the process, the position while queued, keepalives, the journal after the stream expired."""

import asyncio
import json
import threading
import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import boto3
import pytest
import redis
import redis.asyncio
import zstandard
from fastapi.testclient import TestClient
from moto import mock_aws
from test_housekeeping import set_state
from test_ingest import NOW, new_submission, run
from test_submissions_api import RecordingQueue

from apparatica.core.db import Database
from apparatica.core.ids import uuid7
from apparatica.core.settings import Settings
from apparatica.main import create_app
from apparatica.submissions import live
from apparatica.submissions.models import Artifact
from apparatica.submissions.queue import Job
from apparatica.submissions.streams import StreamHub
from conftest import CONFIG_DIR, Postgres
from judge.core.jobs import JudgeJob, submission_stream_key

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

Event = dict[str, Any]  # id (or None), event, data; or comment


@pytest.fixture
def database_url(postgres: Postgres, catalogue_template: str) -> str:
    return postgres.create_database(template=catalogue_template)


@pytest.fixture
def valkey(valkey_url: str) -> str:
    redis.Redis.from_url(valkey_url).flushdb()
    return valkey_url


@pytest.fixture(autouse=True)
def fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live, "KEEPALIVE_S", 0.3)
    monkeypatch.setattr(live, "QUEUE_EVERY_S", 0.1)


@pytest.fixture
def queue() -> RecordingQueue:
    return RecordingQueue()


@pytest.fixture
def s3() -> Iterator["S3Client"]:
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="artifacts")
        yield client


def api(database_url: str, queue: RecordingQueue, queue_url: str | None) -> TestClient:
    settings = Settings(
        environment="test",
        database_url=database_url,
        config_dir=CONFIG_DIR,
        queue_url=queue_url,
        s3_region="us-east-1",
    )
    return TestClient(create_app(settings, job_queue=queue), raise_server_exceptions=False)


def read(client: TestClient, path: str, headers: dict[str, str] | None = None) -> list[Event]:
    """The whole stream: it ends after `finalized`."""
    events: list[Event] = []
    current: Event = {}
    with client.stream("GET", path, headers=headers or {}, timeout=10) as response:
        assert response.status_code == 200, response.read()
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["x-accel-buffering"] == "no"
        for line in response.iter_lines():
            if line.startswith(":"):
                events.append({"comment": line[1:].strip()})
            elif line.startswith("id: "):
                current["id"] = line[4:]
            elif line.startswith("event: "):
                current["event"] = line[7:]
            elif line.startswith("data: "):
                current["data"] = json.loads(line[6:])
            elif not line and current:
                events.append({"id": None} | current)
                current = {}
    return events


def add(url: str, submission: uuid.UUID, *events: Event) -> list[str]:
    client = redis.Redis.from_url(url, decode_responses=True)
    key = submission_stream_key(submission)
    return [str(client.xadd(key, {"e": json.dumps(event)})) for event in events]


def later(seconds: float, action: Any) -> None:
    threading.Timer(seconds, action).start()


FINALIZED = {
    "type": "finalized",
    "status": "accepted",
    "verdict_detail": {"first_failure": None, "limit": None, "warnings": [], "error_codes": []},
}
START = {"type": "stage_start", "attempt": 1, "stage": "lint", "stage_type": "lint", "ordinal": 1}
LOG = {"type": "log", "attempt": 1, "stage": "lint", "ch": "out", "text": "ok\n"}


def test_the_live_stream_continues_after_the_last_event(
    database_url: str, valkey: str, queue: RecordingQueue
) -> None:
    submission = run(database_url, new_submission)
    run(database_url, lambda db: set_state(db, submission, status="running"))
    first, second = add(valkey, submission, START, LOG)
    later(0.4, lambda: add(valkey, submission, FINALIZED))
    with api(database_url, queue, valkey) as client:
        events = read(client, f"/api/v1/submissions/{submission}/events", {"Last-Event-ID": first})
    data = [e for e in events if "event" in e]
    assert [(e["id"], e["event"]) for e in data][:1] == [(second, "log")]
    assert data[0]["data"] == LOG
    assert [e["event"] for e in data] == ["log", "finalized"]
    assert data[-1]["data"] == FINALIZED
    assert data[-1]["id"] > second


def test_a_queued_check_shows_its_position_and_keepalives(
    database_url: str, valkey: str, queue: RecordingQueue
) -> None:
    submission = run(database_url, new_submission)
    payload = JudgeJob.model_construct(submission_id=submission)
    asyncio.run(queue.enqueue(Job(queue="judge.light", payload=payload)))
    later(0.8, lambda: add(valkey, submission, START, FINALIZED))
    with api(database_url, queue, valkey) as client:
        events = read(client, f"/api/v1/submissions/{submission}/events")
    positions = [e for e in events if e.get("event") == "queue"]
    assert positions
    assert {(e["id"], e["data"]["position"], e["data"]["eta_s"]) for e in positions} == {
        (None, 1, None)  # not stored, so no id
    }
    assert {"comment": "keepalive"} in events
    assert [e["event"] for e in events if "event" in e][-2:] == ["stage_start", "finalized"]


def test_a_finished_check_is_read_from_its_journal(
    database_url: str, queue: RecordingQueue, s3: "S3Client"
) -> None:
    submission = run(database_url, new_submission)
    journal = [
        {"id": "1793000000000-0", "event": START},
        {"id": None, "event": LOG},  # never reached the stream
        {"id": "1793000000100-0", "event": LOG},
        {"id": "1793000000200-0", "event": {"type": "done", "attempt": 1}},
    ]
    body = b"".join(json.dumps(record).encode() + b"\n" for record in journal)
    s3.put_object(Bucket="artifacts", Key="j", Body=zstandard.ZstdCompressor().compress(body))

    async def finished(database: Database) -> None:
        await set_state(database, submission, status="accepted", verdict_detail={})
        await set_state(database, submission, finished_at=NOW - timedelta(days=400))
        async with database.sessions.begin() as session:
            session.add(
                Artifact(
                    id=uuid7(),
                    submission_id=submission,
                    kind="events",
                    storage_key="j",
                    size_bytes=len(body),
                    sha256="0" * 64,
                )
            )

    run(database_url, finished)
    # No Valkey: a finished check needs none.
    with api(database_url, queue, None) as client:
        path = f"/api/v1/submissions/{submission}/events"
        events = read(client, path + "?from=1793000000000-0")
        everything = read(client, path)
    assert [(e["id"], e["event"]) for e in events] == [
        ("1793000000100-0", "log"),
        ("1793000000200-0", "done"),
        ("1793000000200-1", "finalized"),  # after the journal
    ]
    assert events[-1]["data"] == FINALIZED
    assert [e["event"] for e in everything] == ["stage_start", "log", "done", "finalized"]


def test_a_check_without_a_journal_ends_with_finalized(
    database_url: str, queue: RecordingQueue, s3: "S3Client"
) -> None:
    submission = run(database_url, new_submission)
    detail = {"first_failure": None, "limit": None, "warnings": [], "error_codes": ["X"]}

    async def failed(database: Database) -> None:
        await set_state(
            database,
            submission,
            status="internal_error",
            verdict_detail=detail,
            finished_at=NOW,
        )

    run(database_url, failed)
    with api(database_url, queue, None) as client:
        events = read(client, f"/api/v1/submissions/{submission}/events")
    assert events == [
        {
            "id": f"{int(NOW.timestamp() * 1000)}-0",
            "event": "finalized",
            "data": {"type": "finalized", "status": "internal_error", "verdict_detail": detail},
        }
    ]


def test_errors_come_before_the_stream(database_url: str, queue: RecordingQueue) -> None:
    submission = run(database_url, new_submission)
    with api(database_url, queue, None) as client:
        missing = client.get(f"/api/v1/submissions/{uuid.uuid4()}/events")
        assert (missing.status_code, missing.json()["code"]) == (404, "NOT_FOUND")
        waiting = client.get(f"/api/v1/submissions/{submission}/events")  # no Valkey
        assert (waiting.status_code, waiting.json()["code"]) == (503, "JUDGE_UNAVAILABLE")


def test_one_reader_serves_every_subscriber(valkey: str) -> None:
    async def scenario() -> None:
        hub = StreamHub(redis.asyncio.Redis.from_url(valkey), block_ms=100)
        submission = uuid.uuid4()
        key = submission_stream_key(submission)
        first, second = add(valkey, submission, START, LOG)
        async with hub.subscribe(key, first) as early, hub.subscribe(key, "0-0") as late:
            third = add(valkey, submission, FINALIZED)[0]
            got_early = [await asyncio.wait_for(early.entries.get(), 2) for _ in range(2)]
            got_late = [await asyncio.wait_for(late.entries.get(), 2) for _ in range(3)]
            assert [entry_id for entry_id, _ in got_early] == [second, third]
            assert [entry_id for entry_id, _ in got_late] == [first, second, third]
            assert early.entries.empty()
        assert await hub.history(key, second) == [(third, json.dumps(FINALIZED).encode())]
        await hub.close()

    asyncio.run(scenario())
