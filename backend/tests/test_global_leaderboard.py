"""The global leaderboard of users (T3.9: FR-LB-05, ADR-0006): points for solved problems and
places 1-3 of problem leaderboards, equal points by who reached them first, my row and the rows
around it, the shift for a week, and the counts after a deletion or a change of the catalogue."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import test_leaderboard_ranking as ranking
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from test_account_deletion import Files, set_delete_at
from test_ingest import run
from test_leaderboard_ranking import accepted, check, signed_in
from test_sessions import sign_in

from apparatica.auth.models import User
from apparatica.auth.sessions import COOKIE as SESSION_COOKIE
from apparatica.core.db import Database
from apparatica.judging.housekeeping import AccountPurge, RatingRecount
from apparatica.leaderboards.models import UserRatingSnapshot
from apparatica.problems.models import Problem
from apparatica.problems.progress import record_check
from apparatica.submissions.models import Submission
from conftest import RATING

# The fixtures of the problems with a default profile and of the client.
database_url = ranking.database_url
api = ranking.api

URL = "/api/v1/leaderboard"


def rows(body: dict[str, Any], key: str = "items") -> list[tuple[int, str, int]]:
    """(place, nick, points) of the rows."""
    return [(row["rank"], row["user"]["nick"], row["points"]) for row in body[key]]


def leaderboard(api: TestClient, query: str = "") -> dict[str, Any]:
    response = api.get(URL + query)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def recount(database_url: str, now: datetime | None = None) -> int:
    """The periodic task of the ingestor: how many places it kept today."""

    async def scenario(database: Database) -> int:
        task = RatingRecount(database, RATING)
        if now is not None:
            task = RatingRecount(database, RATING, clock=lambda: now)
        return await task()

    return run(database_url, scenario)


def crowd(api: TestClient, database_url: str) -> dict[str, str]:
    """mux4 (easy): ada leads, bob and dan share place 2, eve matches ada (no place of her own),
    kim is 4th. The cookies of their sessions by nick."""
    cookies = {}
    for nick, delay, ast in (
        ("ada", 0.5, "n1:ada"),
        ("bob", 0.6, "n1:bob"),
        ("dan", 0.6, "n1:dan"),
        ("eve", 0.5, "n1:ada"),
        ("kim", 0.7, "n1:kim"),
    ):
        cookies[nick] = signed_in(api, database_url, nick)
        check(api, database_url, accepted(delay, 500, ast))
    return cookies


def test_points_for_solutions_and_places(api: TestClient, database_url: str) -> None:
    """Easy 1 per solved problem; 3/2/1 for places 1-3, a shared place gives it to both, a
    follower of a group gets none, place 4 none. Equal points: who reached them first."""
    crowd(api, database_url)
    api.cookies.clear()
    body = leaderboard(api)
    assert rows(body) == [
        (1, "ada", 4),
        (2, "bob", 3),
        (3, "dan", 3),
        (4, "eve", 1),
        (5, "kim", 1),
    ]
    assert body["items"][0]["solved"] == {"easy": 1, "medium": 0, "hard": 0}
    assert body["items"][0]["week_delta"] is None  # no snapshot a week ago
    assert (body["total"], body["me"], body["around_me"]) == (5, None, [])
    assert body["formula"] == {
        "version": 1,
        "solved": {"easy": 1, "medium": 3, "hard": 6},
        "places": [3, 2, 1],
    }
    response = api.get(URL)
    assert response.headers["cache-control"] == "public, no-cache"
    assert response.headers["vary"] == "Cookie"


def test_a_run_and_a_rejected_submit_give_no_points(api: TestClient, database_url: str) -> None:
    sign_in(api, database_url)
    check(api, database_url, accepted(0.5, 500, "n1:ada"), kind="run")
    failed = accepted(0.5, 500, "n1:ada")
    failed[2] = failed[2].model_copy(update={"status": "failed", "failure_kind": "wrong"})
    check(api, database_url, failed)
    assert leaderboard(api)["items"] == []
    assert leaderboard(api)["me"] is None


def test_my_row_and_the_rows_around_it(api: TestClient, database_url: str) -> None:
    """FR-LB-05: my row is marked; off the page, up to two rows above and below it come apart
    from the page, without the rows of the page."""
    cookies = crowd(api, database_url)
    api.cookies.set(SESSION_COOKIE, cookies["eve"])
    body = leaderboard(api, "?per_page=2")
    assert rows(body) == [(1, "ada", 4), (2, "bob", 3)]
    assert body["me"]["rank"] == 4
    assert body["me"]["is_me"]
    assert rows(body, "around_me") == [(3, "dan", 3), (4, "eve", 1), (5, "kim", 1)]
    assert [row["is_me"] for row in body["around_me"]] == [False, True, False]
    assert api.get(URL).headers["cache-control"] == "private, no-store"
    # On the page: nothing around it.
    body = leaderboard(api, "?page=2&per_page=2")
    assert rows(body) == [(3, "dan", 3), (4, "eve", 1)]
    assert body["me"]["rank"] == 4
    assert body["around_me"] == []
    # No points: no row of mine.
    signed_in(api, database_url, "zoe")
    body = leaderboard(api, "?per_page=2")
    assert (body["me"], body["around_me"]) == (None, [])


def test_levels_and_unpublished_problems(api: TestClient, database_url: str) -> None:
    """A solved medium problem gives 3; a problem that is no longer published counts nothing
    (its points go with the next count of the ingestor)."""
    ada = sign_in(api, database_url)
    check(api, database_url, accepted(0.5, 500, "n1:ada"))

    async def solve_fifo(database: Database) -> None:
        async with database.sessions.begin() as session:
            fifo = await session.scalar(select(Problem).where(Problem.slug == "sync-fifo"))
            mux4 = await session.scalar(select(Submission.id).where(Submission.user_id == ada.id))
            assert fifo is not None
            assert fifo.current_version_id is not None
            assert mux4 is not None
            await record_check(
                session,
                user_id=ada.id,
                problem_version_id=fifo.current_version_id,
                submission_id=mux4,
                kind="submit",
                status="accepted",
                finished_at=datetime.now(UTC),
            )

    run(database_url, solve_fifo)
    recount(database_url)
    [row] = leaderboard(api)["items"]
    assert (row["points"], row["solved"]) == (1 + 3 + 3, {"easy": 1, "medium": 1, "hard": 0})

    async def unpublish(database: Database) -> None:
        async with database.sessions.begin() as session:
            await session.execute(
                update(Problem).where(Problem.slug == "mux4").values(is_published=False)
            )

    run(database_url, unpublish)
    recount(database_url)
    [row] = leaderboard(api)["items"]
    assert (row["points"], row["solved"]) == (3, {"easy": 0, "medium": 1, "hard": 0})


def test_the_shift_for_a_week(api: TestClient, database_url: str) -> None:
    """The ingestor keeps the places once a day; a row compares its place with the latest
    snapshot at least 7 days old. Not ranked then: null."""
    crowd(api, database_url)
    today = datetime.now(UTC)
    assert recount(database_url, today) == 5
    assert recount(database_url, today) == 0  # once a day

    async def week_ago(database: Database) -> None:
        async with database.sessions.begin() as session:
            nicks = {nick: id_ for id_, nick in await session.execute(select(User.id, User.nick))}
            for nick, rank in (("ada", 3), ("eve", 1), ("dan", 3)):
                day = today.date() - timedelta(days=8 if nick == "dan" else 7)
                session.add(UserRatingSnapshot(day=day, user_id=nicks[nick], rank=rank))
            # Older than the kept days: deleted by the next snapshot.
            session.add(UserRatingSnapshot(day=date(2000, 1, 1), user_id=nicks["ada"], rank=1))

    run(database_url, week_ago)
    deltas = {row["user"]["nick"]: row["week_delta"] for row in leaderboard(api)["items"]}
    # The day 7 days ago is the latest one old enough; dan's place of day 8 is not read.
    assert deltas == {"ada": 2, "bob": None, "dan": None, "eve": -3, "kim": None}
    recount(database_url, today + timedelta(days=1))

    async def days(database: Database) -> set[date]:
        async with database.sessions() as session:
            return set(await session.scalars(select(UserRatingSnapshot.day)))

    assert date(2000, 1, 1) not in run(database_url, days)


def test_a_deleted_account_leaves_the_rating(api: TestClient, database_url: str) -> None:
    """The places close up: eve leads the group of ada now and takes place 1 with its bonus."""
    cookies = crowd(api, database_url)
    api.cookies.set(SESSION_COOKIE, cookies["ada"])
    response = api.get("/api/v1/me")
    ada_id = response.json()["id"]
    now = datetime.now(UTC)
    set_delete_at(database_url, ada_id, now - timedelta(seconds=1))

    async def purge(database: Database) -> int:
        return await AccountPurge(database, Files(), "artifacts", RATING, clock=lambda: now)()

    assert run(database_url, purge) == 1
    api.cookies.clear()
    assert rows(leaderboard(api)) == [(1, "eve", 4), (2, "bob", 3), (3, "dan", 3), (4, "kim", 1)]
