"""Signed-in users (T2.7a): their submissions and quotas, the statuses of problems that the ingestor
keeps (FR-USR-06), the catalogue with them (FR-CAT-03), the history with filters (FR-USR-03) and
drafts on the server (FR-EDT-02)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from test_ingest import LINT, SIM, WRONG, run
from test_sessions import sign_in
from test_submissions_api import CODE, MUX4, PROFILE, RecordingQueue, submit

from apparatica.auth.guests import COOKIE as GUEST_COOKIE
from apparatica.auth.sessions import COOKIE as SESSION_COOKIE
from apparatica.core.db import Database
from apparatica.core.settings import Settings
from apparatica.judging.housekeeping import GuestPurge, ProblemStatsRefresh
from apparatica.judging.ingest import Ingestor
from apparatica.judging.retention import load_retention
from apparatica.main import create_app
from apparatica.problems.models import Problem, ProblemStats, ProblemVersion, UserProblemStatus
from apparatica.submissions.models import Submission
from apparatica.submissions.profiles import add_profile
from conftest import CONFIG_DIR, ApiClient, NoStorage, Postgres, repo_version
from judge.core.jobs import AttemptFailedRecord, DoneRecord, ResultRecord


@pytest.fixture
def database_url(postgres: Postgres, catalogue_template: str) -> str:
    """The published problems and a default profile."""
    url = postgres.create_database(template=catalogue_template)

    async def profile(database: Database) -> None:
        async with database.sessions.begin() as session:
            await add_profile(session, PROFILE, default=True)

    run(url, profile)
    return url


@pytest.fixture
def api(database_url: str) -> Iterator[TestClient]:
    # Plain HTTP: the test client keeps the guest and session cookies it gets.
    settings = Settings(
        environment="test", database_url=database_url, config_dir=CONFIG_DIR, cookie_secure=False
    )
    app = create_app(settings, job_queue=RecordingQueue())
    with ApiClient(app, raise_server_exceptions=False) as client:
        yield client


def finish(api: TestClient, database_url: str, submission_id: str, *results: Any) -> None:
    """The worker reports the end of the check: `results` are its stages; without any it failed."""
    tokens = api.app.state.job_tokens  # type: ignore[attr-defined]
    id_ = uuid.UUID(submission_id)
    common = {"submission_id": id_, "attempt": 1, "token": tokens.issue(id_)}
    record: ResultRecord = (
        DoneRecord(**common, results=results, artifacts=())
        if results
        else AttemptFailedRecord(**common, error_code="ATTEMPTS_EXHAUSTED")
    )

    async def scenario(database: Database) -> None:
        await Ingestor(database, tokens, load_retention(CONFIG_DIR)).ingest(record)

    run(database_url, scenario)


def statuses(database_url: str) -> list[tuple[str, datetime | None, str]]:
    """(status, first solved at, last submission) of every row."""

    async def scenario(database: Database) -> list[tuple[str, datetime | None, str]]:
        async with database.sessions() as session:
            rows = await session.scalars(select(UserProblemStatus))
            return [(row.status, row.first_solved_at, str(row.last_submission_id)) for row in rows]

    return run(database_url, scenario)


def authors(database_url: str) -> dict[str, tuple[uuid.UUID | None, uuid.UUID | None]]:
    """(user, guest) of every submission."""

    async def scenario(database: Database) -> dict[str, tuple[uuid.UUID | None, uuid.UUID | None]]:
        async with database.sessions() as session:
            rows = await session.scalars(select(Submission))
            return {str(row.id): (row.user_id, row.guest_id) for row in rows}

    return run(database_url, scenario)


def ids(response: Any) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


def checked(api: TestClient, **fields: Any) -> str:
    response = submit(api, **fields)
    assert response.status_code == 202, response.text
    return str(response.json()["id"])


def test_a_signed_in_user_is_the_author(api: TestClient, database_url: str) -> None:
    guest = checked(api)
    assert GUEST_COOKIE in api.cookies
    user = sign_in(api, database_url)
    response = submit(api)
    assert response.status_code == 202
    assert GUEST_COOKIE not in response.cookies  # a user needs no guest
    mine = response.json()
    # The quotas of users (config/limits.yaml), counted apart from the guest's.
    assert mine["quota"]["checks"] == {"limit": 60, "remaining": 59, "reset_at": None}
    assert mine["quota"]["waveforms"]["limit"] == 20
    stored = authors(database_url)
    assert stored[mine["id"]] == (user.id, None)
    assert stored[guest][0] is None
    assert stored[guest][1] is not None

    # Signed in, the guest's submissions are not the user's; signed out, the other way round.
    assert api.get(f"/api/v1/submissions/{guest}").status_code == 404
    assert api.get(f"/api/v1/submissions/{mine['id']}").status_code == 200
    assert ids(api.get("/api/v1/submissions")) == [mine["id"]]
    api.cookies.delete(SESSION_COOKIE)
    assert api.get(f"/api/v1/submissions/{mine['id']}").status_code == 404
    assert api.get(f"/api/v1/submissions/{mine['id']}/events").status_code == 404
    assert api.post(f"/api/v1/submissions/{mine['id']}/cancel").status_code == 404
    assert ids(api.get("/api/v1/submissions")) == [guest]


def test_users_need_no_captcha(api: TestClient, database_url: str) -> None:
    """A guest is asked for one after 3 checks a minute (FR-GST-05); a user is not."""
    sign_in(api, database_url)
    for _ in range(5):
        checked(api)
    api.cookies.delete(SESSION_COOKIE)
    for _ in range(3):
        checked(api)
    assert submit(api).json()["code"] == "CAPTCHA_REQUIRED"


def test_users_may_check_heavy_problems(api: TestClient, database_url: str) -> None:
    async def heavy(database: Database) -> None:
        async with database.sessions.begin() as session:
            await session.execute(update(ProblemVersion).values(resource_class="heavy"))

    run(database_url, heavy)
    assert submit(api).json()["code"] == "HEAVY_NOT_ALLOWED"
    sign_in(api, database_url)
    checked(api)


def test_the_history_filters_by_problem_and_status(api: TestClient, database_url: str) -> None:
    sign_in(api, database_url)
    wrong = checked(api, kind="submit")
    finish(api, database_url, wrong, LINT, WRONG)
    accepted = checked(api, kind="submit")
    finish(api, database_url, accepted, LINT, SIM)
    other = checked(api, problem="sync-fifo", version=repo_version("sync-fifo"))
    everything = "/api/v1/submissions"
    assert ids(api.get(everything)) == [other, accepted, wrong]
    assert ids(api.get(everything, params={"problem": "mux4"})) == [accepted, wrong]
    assert ids(api.get(everything, params={"status": ["accepted", "queued"]})) == [
        other,
        accepted,
    ]
    filtered = api.get(everything, params={"problem": "mux4", "status": "wrong_answer"})
    assert ids(filtered) == [wrong]
    assert api.get(everything, params={"status": "solved"}).status_code == 422


def test_the_ingestor_keeps_the_statuses_of_a_user(api: TestClient, database_url: str) -> None:
    """Any check that ends tries the problem, an accepted Submit solves it, and a solved problem
    stays solved with the time of the first solution (FR-USR-06)."""
    guest = checked(api, kind="submit")
    finish(api, database_url, guest, LINT, SIM)
    assert statuses(database_url) == []  # a guest's statuses are in the browser
    sign_in(api, database_url)

    run_ = checked(api)
    finish(api, database_url, run_, LINT, SIM)  # a passed Run does not solve it
    assert statuses(database_url) == [("attempted", None, run_)]
    failed = checked(api, kind="submit")
    finish(api, database_url, failed)  # internal_error
    assert statuses(database_url) == [("attempted", None, failed)]

    accepted = checked(api, kind="submit")
    finish(api, database_url, accepted, LINT, SIM)
    [(status, solved_at, last)] = statuses(database_url)
    assert (status, last) == ("solved", accepted)
    assert solved_at is not None

    wrong = checked(api, kind="submit")
    finish(api, database_url, wrong, LINT, WRONG)
    finish(api, database_url, wrong, LINT, WRONG)  # a redelivered record changes nothing
    assert statuses(database_url) == [("solved", solved_at, wrong)]


def test_the_catalogue_of_a_user(api: TestClient, database_url: str) -> None:
    guest = api.get("/api/v1/problems")
    assert guest.headers["cache-control"].startswith("public")
    assert guest.headers["vary"] == "Cookie"
    assert {item["status"] for item in guest.json()["items"]} == {None}
    assert {level["solved"] for level in guest.json()["progress"]} == {None}
    refused = api.get("/api/v1/problems", params={"status": "solved"})
    assert (refused.status_code, refused.json()["code"]) == (401, "UNAUTHENTICATED")

    sign_in(api, database_url)
    accepted = checked(api, kind="submit")
    finish(api, database_url, accepted, LINT, SIM)
    tried = checked(api, problem="sync-fifo", version=repo_version("sync-fifo"))
    finish(api, database_url, tried, LINT, WRONG)

    response = api.get("/api/v1/problems", params={"per_page": 100})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "Cookie"
    page = response.json()
    mine = {item["slug"]: item["status"] for item in page["items"]}
    assert mine["mux4"] == "solved"
    assert mine["sync-fifo"] == "attempted"
    assert set(mine.values()) == {"solved", "attempted", "not_started"}
    levels = {item["slug"]: item["difficulty"] for item in page["items"]}
    solved = {level["difficulty"]: level["solved"] for level in page["progress"]}
    assert solved[levels["mux4"]] == 1
    assert sum(solved.values()) == 1

    def slugs(*wanted: str) -> list[str]:
        params: dict[str, Any] = {"status": list(wanted), "per_page": 100}
        response = api.get("/api/v1/problems", params=params)
        assert response.json()["total"] == len(response.json()["items"])
        return [item["slug"] for item in response.json()["items"]]

    assert slugs("solved") == ["mux4"]
    assert sorted(slugs("solved", "attempted")) == ["mux4", "sync-fifo"]
    assert "mux4" not in slugs("not_started")
    assert len(slugs("not_started")) == len(mine) - 2


def test_users_count_in_the_acceptance_and_are_not_purged(
    api: TestClient, database_url: str
) -> None:
    guest = checked(api, kind="submit")
    finish(api, database_url, guest, LINT, WRONG)
    sign_in(api, database_url)
    mine = checked(api, kind="submit")
    finish(api, database_url, mine, LINT, SIM)

    async def scenario(database: Database) -> tuple[Any, set[uuid.UUID]]:
        await ProblemStatsRefresh(database)()
        old = datetime.now(UTC) - timedelta(days=30)
        async with database.sessions.begin() as session:
            await session.execute(update(Submission).values(created_at=old))
        await GuestPurge(database, NoStorage(), "artifacts", days=14)()
        async with database.sessions() as session:
            stats = await session.scalar(
                select(ProblemStats)
                .join(Problem, Problem.id == ProblemStats.problem_id)
                .where(Problem.slug == "mux4")
            )
            assert stats is not None
            kept = set(await session.scalars(select(Submission.id)))
            return (stats.authors, stats.accepted_authors), kept

    counts, kept = run(database_url, scenario)
    assert counts == (2, 1)
    assert kept == {uuid.UUID(mine)}


def test_drafts_of_a_user(api: TestClient, database_url: str) -> None:
    draft = "/api/v1/me/drafts/mux4"
    assert api.get(draft).json()["code"] == "UNAUTHENTICATED"
    assert api.put(draft, json={"code": CODE, "problem_version": MUX4}).status_code == 401
    sign_in(api, database_url)
    assert (api.get(draft).status_code, api.get(draft).json()["code"]) == (404, "NOT_FOUND")

    saved = api.put(draft, json={"code": CODE, "problem_version": MUX4})
    assert saved.status_code == 200, saved.text
    assert saved.headers["cache-control"] == "private, no-store"
    again = api.put(draft, json={"code": "// newer\n", "problem_version": MUX4})
    assert again.json()["updated_at"] >= saved.json()["updated_at"]
    response = api.get(draft)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == again.json() | {"code": "// newer\n", "problem_version": MUX4}

    missing = api.put("/api/v1/me/drafts/no-such", json={"code": "", "problem_version": 1})
    assert (missing.status_code, missing.json()["code"]) == (404, "NOT_FOUND")
    invalid = api.put(draft, json={"code": "", "problem_version": 0})
    assert (invalid.status_code, invalid.json()["code"]) == (422, "VALIDATION_ERROR")
    large = api.put(draft, json={"code": "x\n" * 2001, "problem_version": MUX4})
    assert (large.status_code, large.json()["code"]) == (413, "CODE_TOO_LARGE")
    assert api.get("/api/v1/me/drafts/sync-fifo").status_code == 404  # one per problem

    sign_in(api, database_url, "grace")  # drafts are the user's own
    assert api.get(draft).status_code == 404
