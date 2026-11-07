"""The leaderboards of problems that the ingestor keeps (T3.4: FR-LB-01/02/04/06, ADR-0006): one
entry per user, shared places, groups of equal solutions; the place of a Submit in the submission,
in `finalized` and after the deletion of an account."""

import dataclasses
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import aliased
from test_account_deletion import Files, set_delete_at
from test_ingest import LINT, SIM, run
from test_sessions import sign_in
from test_submissions_api import PROFILE, RecordingQueue, submit

from apparatica.auth.models import User
from apparatica.auth.sessions import COOKIE as SESSION_COOKIE
from apparatica.core.db import Database
from apparatica.core.settings import Settings
from apparatica.judging.housekeeping import AccountPurge
from apparatica.judging.ingest import Ingestor
from apparatica.judging.retention import load_retention
from apparatica.leaderboards.models import LeaderboardEntry
from apparatica.main import create_app
from apparatica.submissions.events import FinalizedEvent
from apparatica.submissions.profiles import add_profile
from conftest import CONFIG_DIR, RATING, ApiClient, Postgres
from judge.core.jobs import DoneRecord
from judge.core.stage import StageResult

NEXT_PROFILE = dataclasses.replace(PROFILE, id="sv-2026.11.1")
# The submit pipeline of mux4 and the types of its stages.
SUBMIT = {
    "precheck": "precheck",
    "lint": "lint",
    "sim_full": "sim",
    "synth": "synth",
    "netlist_sim": "sim",
}


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
    settings = Settings(
        environment="test", database_url=database_url, config_dir=CONFIG_DIR, cookie_secure=False
    )
    app = create_app(settings, job_queue=RecordingQueue())
    with ApiClient(app, raise_server_exceptions=False) as client:
        yield client


def accepted(delay: float, area: float, ast: str) -> list[StageResult]:
    """Every stage of the submit pipeline passed, with these metrics and this AST hash."""
    metrics: dict[str, dict[str, Any]] = {
        "precheck": {"code_hash": "0" * 64, "ast_hash": ast},
        "synth": {"critical_path_ns": delay, "area_um2": area, "cells": 40},
    }
    return [
        StageResult(
            key=key, type=type_, ordinal=ordinal, status="passed", metrics=metrics.get(key, {})
        )
        for ordinal, (key, type_) in enumerate(SUBMIT.items())
    ]


def check(
    api: TestClient, database_url: str, results: list[StageResult], kind: str = "submit"
) -> tuple[str, FinalizedEvent | None]:
    """A check of the client's author that ends with `results`: its id and `finalized`."""
    response = submit(api, kind=kind)
    assert response.status_code == 202, response.text
    submission_id = uuid.UUID(response.json()["id"])
    tokens = api.app.state.job_tokens  # type: ignore[attr-defined]
    record = DoneRecord(
        submission_id=submission_id,
        attempt=1,
        token=tokens.issue(submission_id),
        results=tuple(results),
        artifacts=(),
    )

    async def scenario(database: Database) -> FinalizedEvent | None:
        return await Ingestor(database, tokens, load_retention(CONFIG_DIR), RATING).ingest(record)

    return str(submission_id), run(database_url, scenario)


def placement(api: TestClient, submission_id: str) -> Any:
    response = api.get(f"/api/v1/submissions/{submission_id}")
    assert response.status_code == 200, response.text
    return response.json()["leaderboard"]


def board(database_url: str) -> list[tuple[str, int | None, str | None]]:
    """(nick, place, nick of the leader of the group) of every entry, by place and time."""

    async def scenario(database: Database) -> list[tuple[str, int | None, str | None]]:
        leader = aliased(LeaderboardEntry)
        leader_user = aliased(User)
        async with database.sessions() as session:
            rows = await session.execute(
                select(User.nick, LeaderboardEntry.rank, leader_user.nick)
                .join(User, User.id == LeaderboardEntry.user_id)
                .outerjoin(leader, leader.id == LeaderboardEntry.group_leader_entry_id)
                .outerjoin(leader_user, leader_user.id == leader.user_id)
                .order_by(LeaderboardEntry.sort_values, LeaderboardEntry.submitted_at)
            )
            return [tuple(row) for row in rows]  # type: ignore[misc]

    return run(database_url, scenario)


def test_equal_metrics_share_a_place(api: TestClient, database_url: str) -> None:
    """FR-LB-01: three solutions with 0.71 ns and 744 µm² share place 1, the next one is 4th."""
    ids = {}
    for nick in ("ada", "bob", "eve"):
        sign_in(api, database_url, nick=nick)
        ids[nick], _ = check(api, database_url, accepted(0.71, 744, f"n1:{nick}"))
    sign_in(api, database_url, nick="dan")
    dan, event = check(api, database_url, accepted(0.71, 744.01, "n1:dan"))
    assert board(database_url) == [
        ("ada", 1, None),
        ("bob", 1, None),
        ("eve", 1, None),
        ("dan", 4, None),
    ]
    mine = {"rank": 4, "total": 4, "better_than": 0, "is_best": True, "duplicate_of": None}
    assert event is not None
    assert event.leaderboard is not None
    assert event.leaderboard.model_dump() == mine
    assert placement(api, dan) == mine
    response = api.get(f"/api/v1/submissions/{dan}")
    assert response.json()["public"] is True


def test_a_user_has_one_entry_the_best(api: TestClient, database_url: str) -> None:
    """FR-LB-02: a worse Submit keeps the entry, a better one takes it, an equal later one not."""
    sign_in(api, database_url, nick="bob")
    check(api, database_url, accepted(0.5, 500, "n1:bob"))  # place 1, ada is 2nd
    sign_in(api, database_url)
    first, _ = check(api, database_url, accepted(0.8, 800, "n1:a"))
    worse, event = check(api, database_url, accepted(0.9, 100, "n1:b"))  # delay ranks first
    assert event is not None
    assert event.leaderboard is not None
    assert (event.leaderboard.rank, event.leaderboard.is_best) == (2, False)
    assert placement(api, first)["is_best"] is True
    better, _ = check(api, database_url, accepted(0.4, 900, "n1:c"))
    again, _ = check(api, database_url, accepted(0.4, 900, "n1:d"))
    assert board(database_url) == [("ada", 1, None), ("bob", 2, None)]
    assert placement(api, better) == {
        "rank": 1,
        "total": 2,
        "better_than": 1,
        "is_best": True,
        "duplicate_of": None,
    }
    for other in (first, worse, again):
        assert placement(api, other)["is_best"] is False


def test_equal_solutions_group_under_the_earliest(api: TestClient, database_url: str) -> None:
    """FR-LB-04: the earliest of equal syntax trees holds the place, a later one follows it
    without a place of its own and stays solved; a better solution of the leader hands the group
    to the next one."""
    ada = signed_in(api, database_url, "ada")
    first, _ = check(api, database_url, accepted(0.71, 744, "n1:same"))
    bob = signed_in(api, database_url, "bob")
    copy, _ = check(api, database_url, accepted(0.71, 744, "n1:same"))
    signed_in(api, database_url, "eve")
    check(api, database_url, accepted(0.8, 700, "n1:eve"))
    assert board(database_url) == [("ada", 1, None), ("bob", None, "ada"), ("eve", 2, None)]
    api.cookies.set(SESSION_COOKIE, bob)
    assert placement(api, copy) == {
        "rank": 1,
        "total": 3,
        "better_than": 0.5,
        "is_best": True,
        "duplicate_of": first,
    }
    assert api.get("/api/v1/problems?status=solved").json()["total"] == 1

    api.cookies.set(SESSION_COOKIE, ada)
    check(api, database_url, accepted(0.7, 744, "n1:new"))  # no longer the same tree
    assert board(database_url) == [("ada", 1, None), ("bob", 2, None), ("eve", 3, None)]


def signed_in(api: TestClient, database_url: str, nick: str) -> str:
    """A new user signed in on the client: the cookie of the session, to come back to it."""
    sign_in(api, database_url, nick=nick)
    token = api.cookies.get(SESSION_COOKIE)
    assert token is not None
    return token


def test_what_does_not_rank(api: TestClient, database_url: str) -> None:
    """Only an accepted Submit of a signed-in user is public, and it ranks only with every stage
    of submit passed (FR-LB-02, FR-JDG-13); a Run never does."""
    guest, _ = check(api, database_url, accepted(0.5, 500, "n1:guest"))
    sign_in(api, database_url)
    run_, _ = check(api, database_url, accepted(0.5, 500, "n1:run"), kind="run")
    unranked, event = check(api, database_url, [LINT, SIM])  # accepted without synthesis
    netlist = accepted(0.5, 500, "n1:net")
    netlist[-1] = netlist[-1].model_copy(update={"status": "failed", "failure_kind": "wrong"})
    wrong, _ = check(api, database_url, netlist)
    assert event is not None
    assert (event.status, event.leaderboard) == ("accepted", None)
    assert board(database_url) == []
    statuses = {run_: "accepted", unranked: "accepted", wrong: "wrong_answer"}
    for submission_id, public in ((run_, False), (unranked, True), (wrong, False)):
        found = api.get(f"/api/v1/submissions/{submission_id}").json()
        assert found["status"] == statuses[submission_id]
        assert (found["public"], found["leaderboard"]) == (public, None)
    api.cookies.delete(SESSION_COOKIE)
    assert api.get(f"/api/v1/submissions/{guest}").json()["public"] is False


def test_the_place_is_in_the_event_stream(api: TestClient, database_url: str) -> None:
    """A stream of a finished check ends with `finalized` from the database, with the place."""
    sign_in(api, database_url)
    submission_id, _ = check(api, database_url, accepted(0.5, 500, "n1:a"))
    response = api.get(f"/api/v1/submissions/{submission_id}/events")
    assert response.status_code == 200, response.text
    [data] = [line for line in response.text.splitlines() if line.startswith("data:")]
    event = FinalizedEvent.model_validate_json(data.removeprefix("data:"))
    assert event.leaderboard is not None
    assert (event.leaderboard.rank, event.leaderboard.total) == (1, 1)


def test_another_default_profile_shows_another_leaderboard(
    api: TestClient, database_url: str
) -> None:
    """A place is that of the leaderboard pages show: the default profile (ADR-0006)."""
    sign_in(api, database_url)
    submission_id, _ = check(api, database_url, accepted(0.5, 500, "n1:a"))
    assert placement(api, submission_id) is not None

    async def switch(database: Database) -> None:
        async with database.sessions.begin() as session:
            await add_profile(session, NEXT_PROFILE, default=True)

    run(database_url, switch)
    assert placement(api, submission_id) is None


def test_a_deleted_account_leaves_its_leaderboards(api: TestClient, database_url: str) -> None:
    """The entries go with the account (until ОВ-12 is done, T3.4a) and the places close up."""
    ada = sign_in(api, database_url)
    check(api, database_url, accepted(0.5, 500, "n1:ada"))
    signed_in(api, database_url, "bob")
    check(api, database_url, accepted(0.5, 500, "n1:ada"))
    signed_in(api, database_url, "eve")
    eve, _ = check(api, database_url, accepted(0.6, 500, "n1:eve"))
    assert board(database_url) == [("ada", 1, None), ("bob", None, "ada"), ("eve", 2, None)]
    now = datetime.now(UTC)
    set_delete_at(database_url, ada.id, now - timedelta(seconds=1))

    async def purge(database: Database) -> int:
        return await AccountPurge(database, Files(), "artifacts", RATING, clock=lambda: now)()

    assert run(database_url, purge) == 1
    assert board(database_url) == [("bob", 1, None), ("eve", 2, None)]
    assert placement(api, eve) == {
        "rank": 2,
        "total": 2,
        "better_than": 0,
        "is_best": True,
        "duplicate_of": None,
    }
