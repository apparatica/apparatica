"""Runs of reference solutions (T3.3: FR-SYN-04): the leading ingestor queues a Submit of every
reference solution of a current version on the default toolchain profile, again after the profile
changes; the metrics of a reference are those of its latest accepted run."""

import uuid
from datetime import timedelta
from typing import Any

import test_leaderboard_ranking as ranking
from sqlalchemy import func, select, update
from test_ingest import NOW, TOKENS, run
from test_leaderboard_ranking import NEXT_PROFILE, SETS, SUBMIT
from test_submissions_api import PROFILE, RecordingQueue

from apparatica.core.db import Database
from apparatica.judging.housekeeping import ProblemStatsRefresh, ReferenceRuns
from apparatica.judging.ingest import Ingestor
from apparatica.judging.retention import load_retention
from apparatica.leaderboards.models import LeaderboardEntry
from apparatica.problems.models import Problem, ProblemStats, ProblemVersion, ReferenceSolution
from apparatica.submissions.models import Submission
from apparatica.submissions.profiles import add_profile
from conftest import CONFIG_DIR, RATING, Postgres
from judge.core.jobs import REJUDGE_QUEUE, DoneRecord
from judge.core.stage import StageResult

database_url = ranking.database_url  # the published problems and a default profile
RETRY = timedelta(hours=1)
# A run that fails a test: a verdict, final like an accepted one.
SUBMIT_FAILED = StageResult(
    key="sim_full", type="sim", ordinal=2, status="failed", failure_kind="wrong"
)


def queue_runs(database_url: str, queue: RecordingQueue, now: Any = NOW) -> int:
    async def scenario(database: Database) -> int:
        return await ReferenceRuns(database, queue, TOKENS, RETRY.total_seconds(), lambda: now)()

    return run(database_url, scenario)


def current_references(database_url: str) -> dict[uuid.UUID, tuple[str, str]]:
    """The reference solutions of the current versions: id → (slug, code)."""

    async def scenario(database: Database) -> dict[uuid.UUID, tuple[str, str]]:
        async with database.sessions() as session:
            rows = await session.execute(
                select(ReferenceSolution.id, Problem.slug, ReferenceSolution.code)
                .join(ProblemVersion, ProblemVersion.id == ReferenceSolution.problem_version_id)
                .join(Problem, Problem.current_version_id == ProblemVersion.id)
            )
            return {id: (slug, code) for id, slug, code in rows}

    return run(database_url, scenario)


def runs(database_url: str) -> list[Submission]:
    async def scenario(database: Database) -> list[Submission]:
        async with database.sessions() as session:
            found = await session.scalars(
                select(Submission)
                .where(Submission.reference_solution_id.is_not(None))
                .order_by(Submission.created_at, Submission.id)
            )
            return list(found)

    return run(database_url, scenario)


def end_run(database_url: str, submission_id: uuid.UUID, results: list[StageResult]) -> None:
    record = DoneRecord(
        submission_id=submission_id,
        attempt=1,
        token=TOKENS.issue(submission_id),
        results=tuple(results),
        artifacts=(),
    )

    async def scenario(database: Database) -> None:
        await Ingestor(database, TOKENS, load_retention(CONFIG_DIR), RATING).ingest(record)

    run(database_url, scenario)


def synthesized(synth: dict[str, Any]) -> list[StageResult]:
    """Every stage instance of the submit pipeline of mux4 passed; the synthesis at the primary
    set reported `synth`."""
    metrics: dict[str, dict[str, Any]] = {
        "precheck": {"code_hash": "0" * 64, "ast_hash": "n1:reference"},
        "synth": synth,
    }
    return [
        StageResult(
            key=key,
            type=type_,
            ordinal=ordinal,
            param_set=SETS[key],
            status="passed",
            metrics=metrics.get(key, {}),
        )
        for ordinal, (key, type_) in enumerate(SUBMIT.items())
    ]


def measure_reference(database_url: str, synth: dict[str, Any], slug: str = "mux4") -> None:
    """The runs of the reference solutions of the problem on the default profile end accepted
    with these metrics of the synthesis."""
    queue_runs(database_url, RecordingQueue())
    references = current_references(database_url)
    for submission in runs(database_url):
        assert submission.reference_solution_id is not None
        if (
            submission.status == "queued"
            and references[submission.reference_solution_id][0] == slug
        ):
            end_run(database_url, submission.id, synthesized(synth))


def test_references_of_current_versions_run_on_the_default_profile(
    postgres: Postgres, catalogue_template: str
) -> None:
    """FR-SYN-04: a run of every reference solution of a current version, once."""
    url = postgres.create_database(template=catalogue_template)
    queue = RecordingQueue()
    assert queue_runs(url, queue) == 0  # no default profile: nothing to run on

    async def profile(database: Database) -> None:
        async with database.sessions.begin() as session:
            await add_profile(session, PROFILE, default=True)

    run(url, profile)
    references = current_references(url)
    assert {slug for slug, _ in references.values()} >= {"mux4", "sync-fifo"}
    assert queue_runs(url, queue) == len(references)
    stored = runs(url)
    assert {submission.reference_solution_id for submission in stored} == set(references)
    for submission, job in zip(stored, queue.jobs, strict=True):
        assert job.queue == REJUDGE_QUEUE  # no slot of live users
        assert job.payload.submission_id == submission.id
        slug, code = references[submission.reference_solution_id]  # type: ignore[index]
        assert (job.payload.problem, job.payload.kind, job.payload.code) == (slug, "submit", code)
        assert job.payload.toolchain_profile == PROFILE.id
        assert (submission.user_id, submission.guest_id, submission.is_public) == (
            None,
            None,
            False,
        )
        assert (submission.kind, submission.status) == ("submit", "queued")
        assert submission.toolchain_profile_id == PROFILE.id
        TOKENS.verify(job.payload.token, submission.id)
    assert queue_runs(url, queue) == 0  # waiting runs are not queued again
    assert len(queue.jobs) == len(references)


def test_a_run_without_a_verdict_is_repeated_later(database_url: str) -> None:
    """internal_error and cancelled are repeated after the retry interval; verdicts are final."""
    queue = RecordingQueue()
    queue_runs(database_url, queue)
    failed, wrong, *rest = runs(database_url)
    for submission in rest:
        end_run(database_url, submission.id, synthesized({"area_um2": 1.0}))
    end_run(database_url, wrong.id, [SUBMIT_FAILED])

    async def fail(database: Database) -> None:
        async with database.sessions.begin() as session:
            await session.execute(
                update(Submission)
                .where(Submission.id == failed.id)
                .values(status="internal_error", finished_at=NOW)
            )

    run(database_url, fail)
    assert queue_runs(database_url, queue, NOW + RETRY - timedelta(minutes=1)) == 0
    assert queue_runs(database_url, queue, NOW + RETRY + timedelta(minutes=1)) == 1
    again = queue.jobs[-1].payload.submission_id
    assert [s.reference_solution_id for s in runs(database_url) if s.id == again] == [
        failed.reference_solution_id
    ]


def test_a_new_default_profile_runs_the_references_again(database_url: str) -> None:
    """FR-SYN-04, specs/09 §2: the metrics follow the default profile."""
    queue = RecordingQueue()
    measured = queue_runs(database_url, queue)

    async def switch(database: Database) -> None:
        async with database.sessions.begin() as session:
            await add_profile(session, NEXT_PROFILE, default=True)

    run(database_url, switch)
    assert queue_runs(database_url, queue) == measured
    assert {job.payload.toolchain_profile for job in queue.jobs[measured:]} == {NEXT_PROFILE.id}


def test_an_unreachable_queue_stops_the_round(database_url: str) -> None:
    """The run that could not be queued ends with internal_error; the others wait for the next
    round, the failed one for the retry."""
    queue = RecordingQueue()
    queue.unavailable = True
    assert queue_runs(database_url, queue) == 0
    [failed] = runs(database_url)
    assert failed.status == "internal_error"
    assert (failed.verdict_detail or {})["error_codes"] == ["QUEUE_UNAVAILABLE"]
    queue.unavailable = False
    total = len(current_references(database_url))
    assert queue_runs(database_url, queue) == total - 1
    assert failed.id not in {job.payload.submission_id for job in queue.jobs}


def test_a_run_is_nobody_s_solution(database_url: str) -> None:
    """An accepted run enters no leaderboard and counts no author of the problem."""
    measure_reference(database_url, {"critical_path_ns": 0.3, "area_um2": 200.5})
    [accepted] = [s for s in runs(database_url) if s.status != "queued"]
    assert (accepted.status, accepted.is_public) == ("accepted", False)

    async def scenario(database: Database) -> tuple[int | None, int | None]:
        await ProblemStatsRefresh(database)()
        async with database.sessions() as session:
            entries = await session.scalar(select(func.count()).select_from(LeaderboardEntry))
            authors = await session.scalar(
                select(ProblemStats.authors)
                .join(Problem, Problem.id == ProblemStats.problem_id)
                .where(Problem.slug == "mux4")
            )
            return entries, authors

    assert run(database_url, scenario) == (0, 0)
