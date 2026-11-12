"""The API of the leaderboards of problems, public solutions and reference solutions (T3.5:
FR-LB-01..04, FR-SOL-01..03, FR-REF-01): rows, groups and sorting of a leaderboard, the solutions
of a problem, and the code of others behind the visitor's own accepted Submit."""

import uuid
from typing import Any

import pytest
import test_leaderboard_ranking as ranking
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_ingest import LINT, SIM, run
from test_leaderboard_ranking import NEXT_PROFILE, accepted, check, signed_in
from test_reference_runs import measure_reference
from test_sessions import sign_in
from test_submissions_api import CODE, PROFILE

from apparatica.auth.guests import COOKIE as GUEST_COOKIE
from apparatica.auth.sessions import COOKIE as SESSION_COOKIE
from apparatica.core.db import Database
from apparatica.problems.models import Problem, ProblemVersion
from apparatica.submissions.profiles import add_profile
from judge.core.stage import HiddenTests, StageSummary
from judge.core.stage import TestCase as Case

# The fixtures of the problems with a default profile and of the client.
database_url = ranking.database_url
api = ranking.api

BOARD = "/api/v1/problems/mux4/leaderboard"
SOLUTIONS = "/api/v1/problems/mux4/solutions"
REFERENCE = "/api/v1/problems/mux4/reference"
DELAY, AREA, CELLS = "synth.critical_path_ns", "synth.area_um2", "synth.cells"


def nobody(api: TestClient) -> TestClient:
    """The client without a session and a guest cookie."""
    api.cookies.delete(SESSION_COOKIE)
    api.cookies.delete(GUEST_COOKIE)
    return api


def get(api: TestClient, path: str, **params: Any) -> Any:
    response = api.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def nicks(rows: list[dict[str, Any]]) -> list[tuple[str, int]]:
    return [(row["author"]["nick"], row["rank"]) for row in rows]


def change_manifest(database_url: str, slug: str, **fields: Any) -> None:
    """Set top-level fields of `problem.yaml` of the current version (None removes one)."""

    async def scenario(database: Database) -> None:
        async with database.sessions.begin() as session:
            version = await session.scalar(
                select(ProblemVersion)
                .join(Problem, Problem.current_version_id == ProblemVersion.id)
                .where(Problem.slug == slug)
            )
            assert version is not None
            manifest = {**version.manifest, **fields}
            version.manifest = {key: value for key, value in manifest.items() if value is not None}

    run(database_url, scenario)


@pytest.fixture
def crowd(api: TestClient, database_url: str) -> dict[str, str]:
    """ada and bob share place 1, eve is 3rd, dan repeats eve's syntax tree later: the solution
    ids by nick; the client is signed in as dan."""
    ids = {}
    for nick, delay, area, ast in (
        ("ada", 0.71, 744, "n1:ada"),
        ("bob", 0.71, 744, "n1:bob"),
        ("eve", 0.8, 700, "n1:same"),
        ("dan", 0.8, 700, "n1:same"),
    ):
        sign_in(api, database_url, nick=nick)
        ids[nick], _ = check(api, database_url, accepted(delay, area, ast))
    return ids


def test_a_leaderboard_folds_equal_solutions(
    api: TestClient, database_url: str, crowd: dict[str, str]
) -> None:
    """FR-LB-01, FR-LB-04: shared places, the follower under its leader; nobody gets a public
    answer revalidated by its ETag (FR-LB-06)."""
    response = nobody(api).get(BOARD)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "public, no-cache"
    assert response.headers["vary"] == "Cookie"
    assert api.get(BOARD, headers={"If-None-Match": response.headers["etag"]}).status_code == 304
    body = response.json()
    assert nicks(body["items"]) == [("ada", 1), ("bob", 1), ("eve", 3)]
    assert (body["total"], body["entries"], body["page"], body["per_page"]) == (3, 4, 1, 20)
    assert (body["epoch"], body["toolchain_profile"], body["formula_version"]) == (
        1,
        PROFILE.id,
        1,
    )
    assert body["order"] == [{"metric": DELAY, "dir": "asc"}, {"metric": AREA, "dir": "asc"}]
    assert body["columns"] == [DELAY, AREA, CELLS]
    ada, _, eve = body["items"]
    assert ada["metrics"] == {DELAY: 0.71, AREA: 744, CELLS: 40}
    assert ada["solution_id"] == crowd["ada"]
    assert (ada["is_me"], ada["duplicate_of"], ada["duplicates"], ada["group"]) == (
        False,
        None,
        0,
        [],
    )
    assert eve["duplicates"] == 1
    [member] = eve["group"]
    assert (member["solution_id"], member["author"]["nick"]) == (crowd["dan"], "dan")
    assert body["best"] == ada
    assert (body["me"], body["reference"]) == (None, None)

    flat = get(api, BOARD, group="false")
    assert nicks(flat["items"]) == [("ada", 1), ("bob", 1), ("eve", 3), ("dan", 3)]
    assert flat["total"] == 4
    assert flat["items"][3]["duplicate_of"] == {
        "solution_id": crowd["eve"],
        "author": {"nick": "eve", "display_name": None, "avatar_url": None, "deleted": False},
    }
    assert flat["items"][2]["duplicates"] == 0


def test_sorting_keeps_the_places(
    api: TestClient, database_url: str, crowd: dict[str, str]
) -> None:
    """FR-LB-01: columns sort the rows, the places stay; a metric of no column is 422."""
    assert nicks(get(api, BOARD, sort=AREA)["items"]) == [("eve", 3), ("ada", 1), ("bob", 1)]
    assert nicks(get(api, BOARD, sort=f"-{AREA}")["items"]) == [("ada", 1), ("bob", 1), ("eve", 3)]
    newest = get(api, BOARD, sort="-submitted_at", group="false")["items"]
    assert nicks(newest) == [("dan", 3), ("eve", 3), ("bob", 1), ("ada", 1)]
    for sort in ("synth.flops", "-synth.flops"):
        response = api.get(BOARD, params={"sort": sort})
        assert response.status_code == 422
        assert response.json()["code"] == "VALIDATION_ERROR"


def test_my_row_and_page(api: TestClient, database_url: str, crowd: dict[str, str]) -> None:
    """`me` wherever it is and `around=me`: the page of my row, of my leader when folded."""
    response = api.get(BOARD, params={"around": "me", "per_page": 1, "page": 1})
    assert response.headers["cache-control"] == "private, no-store"
    body = response.json()
    assert body["page"] == 3
    assert nicks(body["items"]) == [("eve", 3)]
    me = body["me"]
    assert (me["author"]["nick"], me["rank"], me["is_me"]) == ("dan", 3, True)
    assert me["duplicate_of"]["solution_id"] == crowd["eve"]
    flat = get(api, BOARD, around="me", per_page=1, group="false")
    assert (flat["page"], nicks(flat["items"])) == (4, [("dan", 3)])
    by_time = get(api, BOARD, around="me", per_page=2, group="false", sort="-submitted_at")
    assert by_time["page"] == 1

    sign_in(api, database_url, nick="zed")  # no entry: the asked page
    body = get(api, BOARD, around="me", per_page=1, page=2)
    assert (body["page"], body["me"]) == (2, None)


def test_a_problem_without_a_leaderboard(api: TestClient, database_url: str) -> None:
    assert api.get("/api/v1/problems/no-such/leaderboard").status_code == 404
    change_manifest(database_url, "mux4", leaderboard=None)
    response = api.get(BOARD)
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert get(api, SOLUTIONS)["items"] == []


def test_solutions_of_a_problem(api: TestClient, database_url: str) -> None:
    """FR-SOL-03: every public solution, by the formula with the unmeasured ones last; `rank` is
    on the one that holds its author's place."""
    sign_in(api, database_url, nick="ada")
    old, _ = check(api, database_url, [LINT, SIM])  # accepted, but no synthesis
    best, _ = check(api, database_url, accepted(0.5, 500, "n1:a"))
    worse, _ = check(api, database_url, accepted(0.6, 400, "n1:b"))
    check(api, database_url, accepted(0.4, 300, "n1:c"), kind="run")  # a Run is not public
    sign_in(api, database_url, nick="bob")
    bob, _ = check(api, database_url, accepted(0.5, 600, "n1:bob"))

    body = get(nobody(api), SOLUTIONS)
    assert body["total"] == 4
    assert body["code_locked"] is True
    items = body["items"]
    assert [item["id"] for item in items] == [best, bob, worse, old]
    assert [item["rank"] for item in items] == [1, 2, None, None]
    first = items[0]
    assert first["problem"]["slug"] == "mux4"
    assert first["author"]["nick"] == "ada"
    assert first["metrics"] == {DELAY: 0.5, AREA: 500, CELLS: 40}
    assert first["status"] == "accepted"
    assert items[3]["metrics"] == {}
    newest = get(api, SOLUTIONS, sort="-submitted_at", per_page=2, page=2)["items"]
    assert [item["id"] for item in newest] == [best, old]
    by_area = get(api, SOLUTIONS, sort=AREA)["items"]
    assert [item["id"] for item in by_area] == [worse, best, bob, old]
    assert api.get(SOLUTIONS, params={"sort": "synth.flops"}).status_code == 422


def test_code_of_others_opens_after_an_accepted_submit(api: TestClient, database_url: str) -> None:
    """FR-SOL-02: metrics, author and place for everyone; the code for its author, for staff,
    and after an accepted Submit of the problem, of a user or a guest."""
    ada = signed_in(api, database_url, "ada")
    solution, _ = check(api, database_url, accepted(0.5, 500, "n1:a"))
    path = f"/api/v1/solutions/{solution}"
    mine = get(api, path)
    assert (mine["code"], mine["code_locked"]) == (CODE, False)

    page = get(nobody(api), path)
    assert (page["code"], page["code_locked"]) == (None, True)
    assert page["author"]["nick"] == "ada"
    assert page["placement"]["rank"] == 1

    sign_in(api, database_url, nick="bob")
    assert get(api, path)["code_locked"] is True
    check(api, database_url, accepted(0.9, 900, "n1:b"), kind="run")  # a Run opens nothing
    assert get(api, path)["code_locked"] is True
    wrong = accepted(0.9, 900, "n1:b")
    wrong[2] = wrong[2].model_copy(update={"status": "failed", "failure_kind": "wrong"})
    check(api, database_url, wrong)
    assert get(api, path)["code_locked"] is True
    check(api, database_url, [LINT, SIM])  # accepted without a place opens the code
    assert get(api, path)["code"] == CODE
    assert get(api, SOLUTIONS)["code_locked"] is False

    nobody(api)
    check(api, database_url, [LINT, SIM])  # a guest
    assert get(api, path)["code"] == CODE
    assert get(api, SOLUTIONS)["code_locked"] is False

    sign_in(nobody(api), database_url, nick="mod", role="moderator")
    assert get(api, path)["code"] == CODE
    api.cookies.set(SESSION_COOKIE, ada)
    assert get(api, path)["code"] == CODE


def test_a_solution_page(api: TestClient, database_url: str) -> None:
    """FR-SOL-01: the stages without test data, the place, the first place and the reference to
    compare with; what is not a public solution is 404."""
    sign_in(api, database_url, nick="bob")
    check(api, database_url, accepted(0.4, 400, "n1:bob"))
    sign_in(api, database_url, nick="ada", display_name="Ada")
    results = accepted(0.5, 500, "n1:a")
    results[2] = results[2].model_copy(
        update={
            "summary": StageSummary(
                tests=[
                    Case(id="t1", name="a", group="open", status="passed"),
                    Case(id="t2", name="b", group="open", status="passed"),
                ],
                hidden_tests=HiddenTests(total=5, passed=5),
            )
        }
    )
    solution, _ = check(api, database_url, results)
    measure_reference(database_url, {"critical_path_ns": 0.3, "area_um2": 200.5, "flops": 0})

    body = get(nobody(api), f"/api/v1/solutions/{solution}")
    assert body["id"] == solution
    assert body["version"] >= 1
    assert body["language"] == "systemverilog"
    assert body["toolchain_profile"] == PROFILE.id
    assert body["author"]["nick"] == "ada"
    assert body["author"]["display_name"] == "Ada"
    assert body["author"]["solved"] == 1
    assert body["rank"] == 2
    assert body["placement"] == {
        "rank": 2,
        "total": 2,
        "better_than": 0,
        "is_best": True,
        "duplicate_of": None,
    }
    assert body["order"] == [{"metric": DELAY, "dir": "asc"}, {"metric": AREA, "dir": "asc"}]
    assert body["best"] == {DELAY: 0.4, AREA: 400, CELLS: 40}
    assert body["reference"] == {DELAY: 0.3, AREA: 200.5, "synth.flops": 0}
    stages = {stage["key"]: stage for stage in body["stages"]}
    assert list(stages) == list(ranking.SUBMIT)  # every instance of the submit pipeline
    assert stages["precheck"]["metrics"] == {}  # the AST hash is not public
    assert stages["synth"]["metrics"] == {"critical_path_ns": 0.5, "area_um2": 500, "cells": 40}
    assert stages["sim_full"]["tests"] == {"passed": 7, "total": 7}
    assert stages["synth"]["tests"] is None
    # ADR-0014: the set of each instance with the values of the package; the metrics of the
    # extra sets show at their instances and rank nothing (`best`, `reference` above).
    assert stages["precheck"]["param_set"] is None
    assert stages["synth"]["param_set"] == {"id": "default", "values": {"WIDTH": 8}}
    assert stages["synth@narrow"]["param_set"] == {"id": "narrow", "values": {"WIDTH": 1}}
    assert stages["netlist_sim@wide"]["param_set"] == {"id": "wide", "values": {"WIDTH": 32}}
    assert stages["synth@narrow"]["metrics"] == {
        "critical_path_ns": 0.01,
        "area_um2": 1,
        "cells": 1,
    }

    board = get(api, BOARD)
    assert board["reference"] == {
        "title": "case по sel",
        "metrics": {DELAY: 0.3, AREA: 200.5, "synth.flops": 0},
    }

    sign_in(api, database_url, nick="eve")
    run_, _ = check(api, database_url, accepted(0.5, 500, "n1:e"), kind="run")
    for missing in (run_, str(uuid.uuid4())):
        response = api.get(f"/api/v1/solutions/{missing}")
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"


def test_a_later_solution_has_no_placement(api: TestClient, database_url: str) -> None:
    """A solution that does not hold its author's place shows no place of its own."""
    sign_in(api, database_url)
    better, _ = check(api, database_url, accepted(0.5, 500, "n1:a"))
    worse, _ = check(api, database_url, accepted(0.6, 500, "n1:b"))
    body = get(api, f"/api/v1/solutions/{worse}")
    assert (body["rank"], body["placement"]) == (None, None)
    assert body["best"] == get(api, f"/api/v1/solutions/{better}")["metrics"]


def test_reference_solutions(api: TestClient, database_url: str) -> None:
    """FR-REF-01: after_accepted by default, public for everyone, hidden for nobody."""
    response = nobody(api).get(REFERENCE)
    assert response.status_code == 403
    assert response.json()["code"] == "REFERENCE_LOCKED"

    check(api, database_url, [LINT, SIM])  # an accepted Submit of a guest
    body = get(api, REFERENCE)
    assert body["visibility"] == "after_accepted"
    [solution] = body["solutions"]
    assert solution["title"] == "case по sel"
    assert "module mux4" in solution["code"]
    assert solution["explanation_md"]
    assert solution["metrics"] is None

    change_manifest(database_url, "mux4", reference={"visibility": "public", "solutions": []})
    assert nobody(api).get(REFERENCE).status_code == 404  # no solutions listed
    change_manifest(
        database_url,
        "mux4",
        reference={
            "visibility": "public",
            "solutions": [{"file": "reference/mux4.sv", "title": "case по sel"}],
        },
    )
    assert get(api, REFERENCE)["visibility"] == "public"
    change_manifest(
        database_url,
        "mux4",
        reference={
            "visibility": "hidden",
            "solutions": [{"file": "reference/mux4.sv", "title": "case по sel"}],
        },
    )
    response = api.get(REFERENCE)
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_reference_metrics_are_those_of_the_default_profile(
    api: TestClient, database_url: str
) -> None:
    """FR-SYN-04: the metrics of the accepted run on the default profile; after the switch of the
    profile none until the reference runs on the new one."""
    reference = {
        "visibility": "public",
        "solutions": [{"file": "reference/mux4.sv", "title": "case по sel"}],
    }
    change_manifest(database_url, "mux4", reference=reference)
    measure_reference(database_url, {"critical_path_ns": 0.3, "area_um2": 200.5, "cells": 12})
    [solution] = get(nobody(api), REFERENCE)["solutions"]
    assert solution["metrics"] == {DELAY: 0.3, AREA: 200.5, CELLS: 12}
    assert get(api, BOARD)["reference"]["metrics"] == solution["metrics"]

    async def switch(database: Database) -> None:
        async with database.sessions.begin() as session:
            await add_profile(session, NEXT_PROFILE, default=True)

    run(database_url, switch)
    assert get(api, REFERENCE)["solutions"][0]["metrics"] is None
    assert get(api, BOARD)["reference"] is None
    measure_reference(database_url, {"critical_path_ns": 0.4, "area_um2": 210, "cells": 12})
    assert get(api, REFERENCE)["solutions"][0]["metrics"] == {DELAY: 0.4, AREA: 210, CELLS: 12}
