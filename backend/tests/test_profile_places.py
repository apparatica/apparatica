"""The leaderboards in a public profile (T3.10, FR-USR-04): the place in the global leaderboard,
the places held in leaderboards of problems, the public solutions and the share of accepted
Submits."""

from datetime import UTC, datetime, timedelta
from typing import Any

import test_leaderboard_ranking as ranking
from fastapi.testclient import TestClient
from sqlalchemy import update
from test_account_deletion import set_delete_at
from test_global_leaderboard import crowd
from test_ingest import run
from test_leaderboard_ranking import NEXT_PROFILE, accepted, check
from test_sessions import sign_in
from test_submissions_api import submit

from apparatica.core.db import Database
from apparatica.problems.models import Problem
from apparatica.submissions.profiles import add_profile

# The fixtures of the problems with a default profile and of the client.
database_url = ranking.database_url
api = ranking.api


def profile(api: TestClient, nick: str) -> dict[str, Any]:
    response = api.get(f"/api/v1/users/{nick}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def solutions(api: TestClient, nick: str, query: str = "") -> dict[str, Any]:
    response = api.get(f"/api/v1/users/{nick}/solutions{query}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_places_in_the_profile(api: TestClient, database_url: str) -> None:
    """ada leads mux4, bob and dan share place 2, eve matches ada and holds no place of her own,
    kim is 4th of 5 authors."""
    crowd(api, database_url)
    api.cookies.clear()
    order = api.get("/api/v1/problems/mux4/leaderboard").json()["order"]
    ada = profile(api, "ada")
    assert ada["rating"] == {"rank": 1, "total": 5, "points": 4, "week_delta": None}
    [place] = ada["best_places"]
    assert {key: place[key] for key in ("rank", "entries", "order")} == {
        "rank": 1,
        "entries": 5,
        "order": order,
    }
    assert place["problem"]["slug"] == "mux4"
    assert place["solution_id"] == solutions(api, "ada")["items"][0]["id"]
    assert (ada["solutions"], ada["submits"]) == (1, {"accepted": 1, "total": 1})
    assert [item["rank"] for item in profile(api, "dan")["best_places"]] == [2]
    assert [item["rank"] for item in profile(api, "kim")["best_places"]] == [4]
    eve = profile(api, "eve")
    assert (eve["best_places"], eve["solutions"]) == ([], 1)
    assert eve["rating"]["rank"] == 4

    # A leaderboard pages no longer show holds no place.
    async def switch(database: Database) -> None:
        async with database.sessions.begin() as session:
            await add_profile(session, NEXT_PROFILE, default=True)

    run(database_url, switch)
    ada = profile(api, "ada")
    assert ada["best_places"] == []
    assert solutions(api, "ada")["items"][0]["rank"] is None


def test_public_solutions_of_a_user(api: TestClient, database_url: str) -> None:
    """Newest first, with the metrics of the formula and the place of the entry: a later worse
    solution has none, the duplicate of eve shows the place of ada's."""
    crowd(api, database_url)
    sign_in(api, database_url, nick="zed")  # no solutions
    api.cookies.clear()
    first = solutions(api, "ada")["items"][0]["id"]
    zed = solutions(api, "zed")
    assert (zed["items"], zed["total"]) == ([], 0)

    page = solutions(api, "eve")
    [eve] = page["items"]
    assert (eve["rank"], eve["duplicate_of"]["solution_id"]) == (1, first)
    assert eve["duplicate_of"]["author"]["nick"] == "ada"
    assert eve["author"]["nick"] == "eve"
    assert eve["problem"]["slug"] == "mux4"
    assert eve["metrics"] == {
        "synth.critical_path_ns": 0.5,
        "synth.area_um2": 500,
        "synth.cells": 40,
    }
    response = api.get("/api/v1/users/eve/solutions")
    assert response.headers["cache-control"].startswith("public")
    assert "code" not in eve


def test_pages_counts_and_hidden_users(api: TestClient, database_url: str) -> None:
    ada = sign_in(api, database_url)
    best, _ = check(api, database_url, accepted(0.5, 500, "n1:a"))
    later, _ = check(api, database_url, accepted(0.6, 500, "n1:b"))
    check(api, database_url, accepted(0.4, 400, "n1:c"), kind="run")  # no Submit
    wrong = accepted(0.5, 500, "n1:d")
    wrong[2] = wrong[2].model_copy(update={"status": "failed", "failure_kind": "wrong"})
    check(api, database_url, wrong)
    assert submit(api, kind="submit").status_code == 202  # no verdict yet
    api.cookies.clear()

    body = solutions(api, "ada", "?per_page=1")
    assert ([item["id"] for item in body["items"]], body["total"]) == ([later], 2)
    assert body["items"][0]["rank"] is None  # the entry is the better one
    body = solutions(api, "ada", "?page=2&per_page=1")
    assert [(item["id"], item["rank"]) for item in body["items"]] == [(best, 1)]
    found = profile(api, "ada")
    assert (found["solutions"], found["submits"]) == (2, {"accepted": 2, "total": 3})

    async def unpublish(database: Database) -> None:
        async with database.sessions.begin() as session:
            await session.execute(
                update(Problem).where(Problem.slug == "mux4").values(is_published=False)
            )

    run(database_url, unpublish)
    found = profile(api, "ada")
    assert (found["solutions"], found["submits"], found["best_places"]) == (
        0,
        {"accepted": 0, "total": 0},
        [],
    )
    assert solutions(api, "ada")["items"] == []

    set_delete_at(database_url, ada.id, datetime.now(UTC) + timedelta(days=7))
    for path in (
        "/api/v1/users/ada",
        "/api/v1/users/ada/solutions",
        "/api/v1/users/nobody/solutions",
    ):
        response = api.get(path)
        assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")
