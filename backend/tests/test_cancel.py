"""Cancellation (specs/07 §3, FR-JDG-10, FR-RUN-07): the endpoint, preemption of an older Run, the
key and the message on Valkey, the ingestor ending a check that waits."""

import asyncio
import json
import uuid
from typing import Any, cast

import pytest
import redis
import redis.asyncio
from fastapi.testclient import TestClient
from test_housekeeping import set_state, status
from test_ingest import LINT, common, ingestor, new_submission, run
from test_submissions_api import CODE, PROFILE, RecordingQueue

from apparatica.core.db import Database
from apparatica.core.platform import SolutionLimits
from apparatica.core.settings import Settings
from apparatica.judging.cancels import CancelWatcher
from apparatica.main import create_app
from apparatica.submissions import service
from apparatica.submissions.events import FinalizedEvent
from apparatica.submissions.profiles import add_profile
from apparatica.submissions.queue import DramatiqQueue
from apparatica.submissions.schemas import SubmissionCreate
from apparatica.submissions.tokens import JobTokens
from conftest import CONFIG_DIR, Postgres
from judge.core.jobs import CANCEL_CHANNEL, DoneRecord, cancel_key, submission_stream_key
from judge.core.verdict import VerdictDetail

CANCELLED = FinalizedEvent(status="cancelled", verdict_detail=VerdictDetail())


@pytest.fixture
def database_url(postgres: Postgres, catalogue_template: str) -> str:
    return postgres.create_database(template=catalogue_template)


def api(database_url: str, queue: RecordingQueue) -> TestClient:
    settings = Settings(environment="test", database_url=database_url, config_dir=CONFIG_DIR)
    return TestClient(create_app(settings, job_queue=queue), raise_server_exceptions=False)


def test_the_endpoint_asks_to_cancel_an_unfinished_check(database_url: str) -> None:
    queued, running, finished = [run(database_url, new_submission) for _ in range(3)]
    run(database_url, lambda db: set_state(db, running, status="running"))
    run(database_url, lambda db: set_state(db, finished, status="accepted"))
    queue = RecordingQueue()
    with api(database_url, queue) as client:
        for submission in (queued, running):
            response = client.post(f"/api/v1/submissions/{submission}/cancel")
            assert (response.status_code, response.content) == (202, b"")
        done = client.post(f"/api/v1/submissions/{finished}/cancel")
        assert (done.status_code, done.json()["code"]) == (409, "SUBMISSION_FINISHED")
        missing = client.post(f"/api/v1/submissions/{uuid.uuid4()}/cancel")
        assert missing.status_code == 404
        queue.unavailable = True
        down = client.post(f"/api/v1/submissions/{queued}/cancel")
        assert (down.status_code, down.json()["code"]) == (503, "JUDGE_UNAVAILABLE")
    assert queue.cancels == [(queued, "user"), (running, "user")]
    # The status changes only when the ingestor stores the cancel.
    assert run(database_url, lambda db: status(db, queued))[0] == "queued"


def test_a_new_run_preempts_the_unfinished_runs_of_its_author(database_url: str) -> None:
    guest, other = uuid.uuid4(), uuid.uuid4()
    queue = RecordingQueue()

    async def scenario(database: Database) -> list[uuid.UUID]:
        async def create(kind: str, author: uuid.UUID, problem: str = "mux4") -> uuid.UUID:
            request = SubmissionCreate.model_validate(
                {"problem": problem, "version": 1, "kind": kind, "code": CODE}
            )
            async with database.sessions() as session:
                created = await service.create_submission(
                    session,
                    request,
                    limits=SolutionLimits(max_bytes=65536, max_lines=2000),
                    tokens=JobTokens(b"k" * 32, ttl_s=60),
                    queue=queue,
                    guest_id=author,
                )
            return created.id

        async with database.sessions.begin() as session:
            await add_profile(session, PROFILE, default=True)
        first = await create("run", guest)
        submit = await create("submit", guest)  # a Submit is never preempted
        others = await create("run", other)  # another author
        sync_fifo = await create("run", guest, "sync-fifo")  # another problem
        second = await create("run", guest)  # preempts `first`
        return [first, submit, others, sync_fifo, second]

    first, *_, second = run(database_url, scenario)
    assert queue.cancels == [(first, "preempted")]
    assert second != first


def test_the_queue_sets_the_key_and_publishes(valkey_url: str) -> None:
    async def scenario() -> None:
        queue = DramatiqQueue(valkey_url)
        listener = redis.asyncio.Redis.from_url(valkey_url)
        pubsub: Any = listener.pubsub(ignore_subscribe_messages=True)
        await pubsub.subscribe(CANCEL_CHANNEL)
        submission = uuid.uuid4()
        await queue.cancel(submission, "preempted")
        message = None
        for _ in range(20):
            message = await pubsub.get_message(timeout=0.2)
            if message is not None:
                break
        assert message is not None
        assert message["data"] == f"{submission} preempted".encode()
        client = redis.asyncio.Redis.from_url(valkey_url)
        assert await client.get(cancel_key(submission)) == b"preempted"
        assert 0 < await client.ttl(cancel_key(submission)) <= 86400
        await pubsub.aclose()
        await listener.aclose()
        await client.aclose()
        await queue.close()

    asyncio.run(scenario())


def test_the_ingestor_ends_a_waiting_check_at_once(database_url: str, valkey_url: str) -> None:
    async def scenario(database: Database) -> None:
        waiting, running = await new_submission(database), await new_submission(database)
        await set_state(database, running, status="running")
        valkey = redis.asyncio.Redis.from_url(valkey_url)
        watcher = CancelWatcher(valkey, ingestor(database))
        await watcher.handle(f"{waiting} user".encode())
        await watcher.handle(f"{running} user".encode())  # its worker reports it
        await watcher.handle(b"garbage")
        assert await status(database, waiting) == ("cancelled", VerdictDetail().model_dump())
        assert (await status(database, running))[0] == "running"
        entries = cast(
            list[tuple[bytes, dict[bytes, bytes]]],
            await valkey.xrange(submission_stream_key(waiting)),
        )
        assert [json.loads(f[b"e"])["status"] for _, f in entries] == ["cancelled"]
        assert not await valkey.exists(submission_stream_key(running))
        await valkey.aclose()

    run(database_url, scenario)


def test_a_cancelled_attempt_ends_as_cancelled(database_url: str) -> None:
    async def scenario(database: Database) -> None:
        before_start, during = await new_submission(database), await new_submission(database)
        ingest = ingestor(database).ingest
        nothing_ran = DoneRecord(**common(before_start), results=(), artifacts=(), cancelled=True)
        assert await ingest(nothing_ran) == CANCELLED
        stopped = DoneRecord(**common(during), results=(LINT,), artifacts=(), cancelled=True)
        assert await ingest(stopped) == CANCELLED
        # A late cancel of a finished check changes nothing.
        assert await ingestor(database).cancel_waiting(during) is None

    run(database_url, scenario)
