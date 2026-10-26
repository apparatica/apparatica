"""The ingestor (ADR-0009): records of judge:results to Postgres, `finalized` to the submission
stream; idempotent under redelivery, reordering and newer attempts (NFR-REL-02)."""

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
import redis.asyncio
from sqlalchemy import select
from test_submissions_api import PROFILE

from apparatica.core.db import Database
from apparatica.core.ids import uuid7
from apparatica.core.settings import Settings
from apparatica.judging.consumer import GROUP, ResultsConsumer, run_ingest
from apparatica.judging.ingest import Ingestor, InvalidRecordError
from apparatica.judging.retention import load_retention
from apparatica.problems.models import Problem, ProblemVersion
from apparatica.submissions.events import FinalizedEvent
from apparatica.submissions.models import Artifact, StageResult, Submission
from apparatica.submissions.profiles import add_profile
from apparatica.submissions.tokens import JobTokens
from conftest import CONFIG_DIR, Postgres
from judge.core.jobs import (
    RESULTS_STREAM,
    AttemptFailedRecord,
    AttemptStartedRecord,
    DoneRecord,
    ResultRecord,
    StageEndRecord,
    StoredArtifact,
    submission_stream_key,
)
from judge.core.stage import StageResult as Result
from judge.core.stage import StageSummary
from judge.core.stage import TestCase as Case
from judge.core.verdict import FirstFailure, VerdictDetail

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
TOKENS = JobTokens(b"k" * 32, ttl_s=3600)
LINT = Result(key="lint", type="lint", ordinal=1, status="passed", started_at=NOW, duration_ms=5)
SIM = Result(key="sim_run", type="sim", ordinal=2, status="passed", metrics_schema="sim/v1")
WRONG = SIM.model_copy(
    update={
        "status": "failed",
        "failure_kind": "wrong",
        "summary": StageSummary(
            tests=[Case(id="t2", name="x", group="open", status="failed", cycle=7)]
        ),
    }
)


def run[T](url: str, scenario: Callable[[Database], Awaitable[T]]) -> T:
    async def main() -> T:
        database = Database(url)
        try:
            return await scenario(database)
        finally:
            await database.dispose()

    return asyncio.run(main())


@pytest.fixture
def database_url(postgres: Postgres, catalogue_template: str) -> str:
    return postgres.create_database(template=catalogue_template)


async def new_submission(database: Database, kind: str = "run") -> uuid.UUID:
    async with database.sessions.begin() as session:
        await add_profile(session, PROFILE, default=True)
        version = await session.scalar(
            select(ProblemVersion)
            .join(Problem, Problem.current_version_id == ProblemVersion.id)
            .where(Problem.slug == "mux4")
        )
        assert version is not None
        submission = Submission(
            id=uuid7(),
            problem_version_id=version.id,
            kind=kind,
            code="module mux4; endmodule\n",
            seed=1,
            toolchain_profile_id=PROFILE.id,
            queue_class="light",
        )
        session.add(submission)
    return submission.id


def ingestor(database: Database) -> Ingestor:
    return Ingestor(database, TOKENS, load_retention(CONFIG_DIR), clock=lambda: NOW)


def common(submission_id: uuid.UUID, attempt: int = 1) -> dict[str, Any]:
    return {
        "submission_id": submission_id,
        "attempt": attempt,
        "token": TOKENS.issue(submission_id),
    }


def artifact(submission_id: uuid.UUID, kind: str, name: str, attempt: int = 1) -> StoredArtifact:
    return StoredArtifact.model_validate(
        {
            "kind": kind,
            "stage": "sim_run" if kind == "fst" else None,
            "key": f"2026/10/{submission_id}/{attempt}/{name}",
            "size_bytes": 3,
            "sha256": "0" * 64,
        }
    )


async def state(database: Database, submission_id: uuid.UUID) -> dict[str, Any]:
    async with database.sessions() as session:
        submission = await session.get(Submission, submission_id)
        assert submission is not None
        stages = await session.scalars(
            select(StageResult)
            .where(StageResult.submission_id == submission_id)
            .order_by(StageResult.ordinal)
        )
        artifacts = await session.scalars(
            select(Artifact)
            .where(Artifact.submission_id == submission_id)
            .order_by(Artifact.storage_key)
        )
        return {
            "status": submission.status,
            "attempt": submission.attempt,
            "started": submission.started_at is not None,
            "finished": submission.finished_at is not None,
            "detail": submission.verdict_detail,
            "stages": [(s.stage_key, s.status) for s in stages],
            "artifacts": [
                (a.kind, a.storage_key.rsplit("/", 1)[1], a.expires_at) for a in artifacts
            ],
        }


def test_a_check_is_stored_as_it_runs(database_url: str) -> None:
    async def scenario(database: Database) -> None:
        submission = await new_submission(database)
        ingest = ingestor(database).ingest
        assert await ingest(AttemptStartedRecord(**common(submission))) is None
        assert (await state(database, submission))["status"] == "running"
        assert await ingest(StageEndRecord(**common(submission), result=LINT)) is None
        partial = await state(database, submission)
        assert (partial["stages"], partial["finished"]) == ([("lint", "passed")], False)
        done = DoneRecord(
            **common(submission),
            results=(LINT, SIM),
            artifacts=(
                artifact(submission, "log", "logs/lint.log.zst"),
                artifact(submission, "fst", "sim_run/trace.fst"),
            ),
        )
        assert await ingest(done) == FinalizedEvent(
            status="accepted", verdict_detail=VerdictDetail()
        )
        stored = await state(database, submission)
        assert stored | {"artifacts": None} == {
            "status": "accepted",
            "attempt": 1,
            "started": True,
            "finished": True,
            "detail": VerdictDetail().model_dump(mode="json"),
            "stages": [("lint", "passed"), ("sim_run", "passed")],
            "artifacts": None,
        }
        # config/retention.yaml: logs of a Run 30 days, traces 7 days.
        assert stored["artifacts"] == [
            ("log", "lint.log.zst", NOW + timedelta(days=30)),
            ("fst", "trace.fst", NOW + timedelta(days=7)),
        ]

    run(database_url, scenario)


def test_redelivery_and_late_records_change_nothing(database_url: str) -> None:
    async def scenario(database: Database) -> None:
        submission = await new_submission(database, kind="submit")
        ingest = ingestor(database).ingest
        done = DoneRecord(
            **common(submission),
            results=(LINT, WRONG),
            artifacts=(artifact(submission, "log", "logs/sim_run.log.zst"),),
        )
        finalized = await ingest(done)  # attempt_started and stage_end were lost
        assert finalized is not None
        assert finalized.status == "wrong_answer"
        assert finalized.verdict_detail.first_failure == FirstFailure(
            stage="sim_run", test="t2", cycle=7
        )
        before = await state(database, submission)
        assert before["artifacts"] == [("log", "sim_run.log.zst", None)]  # Submit: kept
        # The same done again publishes the same finalized; a late stage_end is void.
        assert await ingest(done) == finalized
        assert await ingest(StageEndRecord(**common(submission), result=SIM)) is None
        assert await state(database, submission) == before

    run(database_url, scenario)


def test_a_new_attempt_voids_the_old_one(database_url: str) -> None:
    async def scenario(database: Database) -> None:
        submission = await new_submission(database)
        ingest = ingestor(database).ingest
        await ingest(AttemptStartedRecord(**common(submission)))
        await ingest(StageEndRecord(**common(submission), result=LINT))
        await ingest(AttemptStartedRecord(**common(submission, 2)))  # the worker died
        assert (await state(database, submission))["stages"] == []
        # The first worker still reports: void.
        await ingest(StageEndRecord(**common(submission, 1), result=SIM))
        assert (
            await ingest(DoneRecord(**common(submission, 1), results=(LINT,), artifacts=())) is None
        )
        await ingest(StageEndRecord(**common(submission, 2), result=LINT))
        exhausted = AttemptFailedRecord(**common(submission, 3), error_code="ATTEMPTS_EXHAUSTED")
        assert await ingest(exhausted) == FinalizedEvent(
            status="internal_error",
            verdict_detail=VerdictDetail(error_codes=["ATTEMPTS_EXHAUSTED"]),
        )
        stored = await state(database, submission)
        assert (stored["attempt"], stored["stages"]) == (2, [("lint", "passed")])

    run(database_url, scenario)


def test_records_without_a_valid_token_or_with_foreign_files_are_refused(
    database_url: str,
) -> None:
    async def scenario(database: Database) -> None:
        submission, other = await new_submission(database), await new_submission(database)
        ingest = ingestor(database).ingest
        forged: list[ResultRecord] = [
            AttemptStartedRecord(**common(submission) | {"token": TOKENS.issue(other)}),
            AttemptStartedRecord(
                **common(submission) | {"token": JobTokens(b"x" * 32, ttl_s=60).issue(submission)}
            ),
            AttemptStartedRecord(**common(uuid.uuid4())),  # no such submission
            # The database refuses what the judge model lets through: failed without a kind.
            StageEndRecord(
                **common(submission), result=SIM.model_copy(update={"status": "failed"})
            ),
        ]
        for record in forged:
            with pytest.raises(InvalidRecordError):
                await ingest(record)
        assert (await state(database, submission))["status"] == "queued"
        done = DoneRecord(
            **common(submission),
            results=(LINT,),
            artifacts=(
                artifact(other, "fst", "sim_run/trace.fst"),  # another check's file
                artifact(submission, "fst", "sim_run/trace.fst", attempt=2),  # another attempt
                artifact(submission, "log", "logs/lint.log.zst"),
            ),
        )
        await ingest(done)
        assert [name for _, name, _ in (await state(database, submission))["artifacts"]] == [
            "lint.log.zst"
        ]

    run(database_url, scenario)


# --- the consumer -------------------------------------------------------------------------------


class Flaky:
    """An ingestor whose database is down for the first `failures` records."""

    def __init__(self, inner: Ingestor, failures: int) -> None:
        self._inner, self.failures = inner, failures

    async def ingest(self, record: ResultRecord) -> FinalizedEvent | None:
        if self.failures:
            self.failures -= 1
            raise ConnectionRefusedError("postgres is down")
        return await self._inner.ingest(record)


def test_the_consumer_applies_acknowledges_and_publishes(
    database_url: str, valkey_url: str
) -> None:
    async def scenario(database: Database) -> None:
        submission = await new_submission(database)
        valkey = redis.asyncio.Redis.from_url(valkey_url)
        await valkey.flushdb()
        flaky = Flaky(ingestor(database), failures=1)
        consumer = ResultsConsumer(valkey, flaky, "ingest-a", block_ms=100)  # type: ignore[arg-type]
        await consumer.ensure_group()
        await consumer.ensure_group()  # a second instance finds the group
        records: list[ResultRecord] = [
            AttemptStartedRecord(**common(submission)),
            DoneRecord(**common(submission), results=(LINT,), artifacts=()),
        ]
        await valkey.xadd(RESULTS_STREAM, {"r": b"not json"})
        for record in records:
            await valkey.xadd(RESULTS_STREAM, {"r": record.model_dump_json()})

        with pytest.raises(ConnectionRefusedError):  # the malformed entry went, the next waits
            await consumer.step()
        assert await valkey.xlen(RESULTS_STREAM) == 2
        while await consumer.step():
            pass
        assert await valkey.xlen(RESULTS_STREAM) == 0  # acknowledged and deleted
        assert (await valkey.xpending(RESULTS_STREAM, GROUP))["pending"] == 0
        assert (await state(database, submission))["status"] == "accepted"
        key = submission_stream_key(submission)
        entries = cast(list[tuple[bytes, dict[bytes, bytes]]], await valkey.xrange(key))
        [(_, fields)] = entries
        assert json.loads(fields[b"e"]) == {
            "type": "finalized",
            "status": "accepted",
            "verdict_detail": VerdictDetail().model_dump(mode="json"),
        }
        assert 0 < await valkey.ttl(key) <= 600
        await valkey.aclose()

    run(database_url, scenario)


def test_entries_of_a_dead_consumer_are_taken_over(database_url: str, valkey_url: str) -> None:
    async def scenario(database: Database) -> None:
        submission = await new_submission(database)
        valkey = redis.asyncio.Redis.from_url(valkey_url)
        await valkey.flushdb()
        dead = ResultsConsumer(valkey, ingestor(database), "ingest-dead")
        await dead.ensure_group()
        await valkey.xadd(
            RESULTS_STREAM, {"r": AttemptStartedRecord(**common(submission)).model_dump_json()}
        )
        # Delivered to the dead consumer and never acknowledged.
        await valkey.xreadgroup(GROUP, "ingest-dead", {RESULTS_STREAM: ">"})
        alive = ResultsConsumer(
            valkey, ingestor(database), "ingest-b", block_ms=100, claim_idle_ms=0
        )
        assert await alive.step() == 1
        assert (await state(database, submission))["status"] == "running"
        assert await valkey.xlen(RESULTS_STREAM) == 0
        await valkey.aclose()

    run(database_url, scenario)


def test_the_ingestor_needs_the_key_of_the_api(database_url: str, valkey_url: str) -> None:
    settings = Settings(environment="test", database_url=database_url, config_dir=CONFIG_DIR)
    with pytest.raises(RuntimeError, match="APX_QUEUE_URL"):
        asyncio.run(run_ingest(settings, asyncio.Event()))
    with pytest.raises(RuntimeError, match="APX_JOB_TOKEN_KEY"):
        asyncio.run(
            run_ingest(settings.model_copy(update={"queue_url": valkey_url}), asyncio.Event())
        )
