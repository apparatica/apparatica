"""The public solutions and places of a deleted account pass to «удалённый участник» (T3.4a,
ОВ-12, FR-USR-05); everything else of the account goes."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import test_leaderboard_ranking as ranking
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from test_account_deletion import Files, set_delete_at
from test_ingest import run
from test_leaderboard_ranking import accepted, board, check, placement
from test_moderation import moderate, rating_nicks, solution_ids, staff
from test_sessions import sign_in

from apparatica.admin.moderation import ModerationRefusedError
from apparatica.auth.models import DELETED_USER_ID, User
from apparatica.core.db import Database
from apparatica.core.ids import uuid7
from apparatica.judging.housekeeping import AccountPurge, ProblemStatsRefresh
from apparatica.problems.models import Problem, ProblemStats, UserProblemStatus
from apparatica.submissions.models import Artifact, Submission, Waveform
from conftest import RATING

database_url = ranking.database_url
api = ranking.api

ANONYMOUS = "deleted-participant"
BOARD = "/api/v1/problems/mux4/leaderboard"


def purge(database_url: str, *user_ids: uuid.UUID, storage: Files | None = None) -> int:
    """The accounts asked deletion and their time came: how many the ingestor deleted."""
    now = datetime.now(UTC)
    for user_id in user_ids:
        set_delete_at(database_url, user_id, now - timedelta(seconds=1))

    async def scenario(database: Database) -> int:
        return await AccountPurge(
            database, storage or Files(), "artifacts", RATING, clock=lambda: now
        )()

    return run(database_url, scenario)


def test_the_solutions_and_places_of_a_deleted_account_stay(
    api: TestClient, database_url: str
) -> None:
    """ОВ-12: nobody's place moves; the author is anonymous everywhere and has no profile."""
    ada = sign_in(api, database_url, nick="ada")
    best, _ = check(api, database_url, accepted(0.5, 500, "n1:ada"))
    worse, _ = check(api, database_url, accepted(0.7, 500, "n1:slow"))
    sign_in(api, database_url, nick="bob")
    bob, _ = check(api, database_url, accepted(0.5, 500, "n1:ada"))  # follows the solution of ada
    sign_in(api, database_url, nick="eve")
    eve, _ = check(api, database_url, accepted(0.6, 500, "n1:eve"))
    assert board(database_url) == [("ada", 1, None), ("bob", None, "ada"), ("eve", 2, None)]

    assert purge(database_url, ada.id) == 1

    assert board(database_url) == [(ANONYMOUS, 1, None), ("bob", None, ANONYMOUS), ("eve", 2, None)]
    assert placement(api, eve)["rank"] == 2
    assert placement(api, eve)["total"] == 3
    page = api.get(BOARD).json()
    assert page["items"][0]["author"] == {
        "nick": ANONYMOUS,
        "display_name": None,
        "avatar_url": None,
        "deleted": True,
    }
    assert page["items"][1]["author"]["deleted"] is False
    assert set(solution_ids(api)) == {best, worse, bob, eve}
    solution = api.get(f"/api/v1/solutions/{best}").json()
    assert solution["author"]["deleted"] is True
    assert solution["placement"]["rank"] == 1
    assert solution["code"] is not None  # the visitor, eve, has an accepted Submit
    assert api.get(f"/api/v1/solutions/{worse}").json()["placement"] is None  # no entry
    assert api.get(f"/api/v1/users/{ANONYMOUS}").status_code == 404
    assert api.get(f"/api/v1/users/{ANONYMOUS}/solutions").status_code == 404
    assert api.get("/api/v1/users/ada").status_code == 404
    assert set(rating_nicks(api)) == {"bob", "eve"}


def test_deleted_accounts_share_the_author_but_not_the_places(
    api: TestClient, database_url: str
) -> None:
    """Many entries of one leaderboard belong to «удалённый участник», one to any other user."""
    ada = sign_in(api, database_url, nick="ada")
    first, _ = check(api, database_url, accepted(0.5, 500, "n1:ada"))
    bob = sign_in(api, database_url, nick="bob")
    second, _ = check(api, database_url, accepted(0.6, 500, "n1:bob"))
    sign_in(api, database_url, nick="eve")
    eve, _ = check(api, database_url, accepted(0.7, 500, "n1:eve"))

    assert purge(database_url, ada.id, bob.id) == 2

    assert board(database_url) == [(ANONYMOUS, 1, None), (ANONYMOUS, 2, None), ("eve", 3, None)]
    places = [
        api.get(f"/api/v1/solutions/{solution}").json()["placement"]["rank"]
        for solution in (first, second)
    ]
    assert places == [1, 2]

    better, _ = check(api, database_url, accepted(0.4, 500, "n1:eve2"))  # still one entry of eve
    assert board(database_url) == [("eve", 1, None), (ANONYMOUS, 2, None), (ANONYMOUS, 3, None)]
    assert placement(api, better)["is_best"] is True
    assert placement(api, eve)["is_best"] is False


def test_only_what_was_public_stays(api: TestClient, database_url: str) -> None:
    """A Run and a hidden Submit go; of the public Submit no address, artifact or waveform stays."""
    ada = sign_in(api, database_url, nick="ada")
    public, _ = check(api, database_url, accepted(0.5, 500, "n1:ada"))
    hidden, _ = check(api, database_url, accepted(0.6, 500, "n1:hidden"))
    check(api, database_url, accepted(0.5, 500, "n1:run"), kind="run")
    storage = Files()
    storage.put("artifacts", "ada-log", b"x", "text/plain")

    async def scenario(database: Database) -> None:
        async with database.sessions.begin() as session:
            await session.execute(
                update(Submission)
                .where(Submission.id == uuid.UUID(public))
                .values(client_ip_hash="ab" * 32)
            )
            await session.execute(
                update(Submission).where(Submission.id == uuid.UUID(hidden)).values(is_hidden=True)
            )
            session.add(
                Artifact(
                    id=uuid7(),
                    submission_id=uuid.UUID(public),
                    kind="log",
                    storage_key="ada-log",
                    size_bytes=1,
                    sha256="0" * 64,
                )
            )
            session.add(
                Waveform(
                    id=uuid7(),
                    submission_id=uuid.UUID(public),
                    stage_key="sim_full",
                    status="failed",
                    error_code="X",
                )
            )

    run(database_url, scenario)
    assert purge(database_url, ada.id, storage=storage) == 1

    async def left(database: Database) -> None:
        async with database.sessions() as session:
            found = (await session.scalars(select(Submission))).all()
            assert [str(item.id) for item in found] == [public]
            assert found[0].user_id == DELETED_USER_ID
            assert found[0].client_ip_hash is None
            for table in (Artifact, Waveform):
                assert await session.scalar(select(func.count()).select_from(table)) == 0
            assert await session.scalar(select(func.count()).select_from(UserProblemStatus)) == 0
            assert await session.scalar(select(User.id).where(User.id == ada.id)) is None

    run(database_url, left)
    assert storage.objects == {}


def test_a_user_hidden_by_a_moderator_leaves_nothing(api: TestClient, database_url: str) -> None:
    """Hidden solutions are not public, and must not come back under another name."""
    ada = sign_in(api, database_url, nick="ada")
    check(api, database_url, accepted(0.5, 500, "n1:ada"))
    sign_in(api, database_url, "mod", role="moderator")
    mod = staff(database_url, "mod")
    moderate(
        database_url,
        lambda moderation: moderation.hide_users(mod, [ada.id], hidden=True, reason="spam"),
    )

    assert purge(database_url, ada.id) == 1

    assert board(database_url) == []
    assert solution_ids(api) == []


def test_a_moderator_hides_one_solution_of_the_deleted(api: TestClient, database_url: str) -> None:
    """The entries of other deleted authors stay; shown again, the solution has no place."""
    ada = sign_in(api, database_url, nick="ada")
    first, _ = check(api, database_url, accepted(0.5, 500, "n1:ada"))
    bob = sign_in(api, database_url, nick="bob")
    second, _ = check(api, database_url, accepted(0.6, 500, "n1:bob"))
    assert purge(database_url, ada.id, bob.id) == 2
    sign_in(api, database_url, "mod", role="moderator")
    mod = staff(database_url, "mod")

    def hide(hidden: bool) -> int:
        return moderate(
            database_url,
            lambda moderation: moderation.hide_submissions(
                mod, [uuid.UUID(first)], hidden=hidden, reason="copied"
            ),
        )

    assert hide(True) == 1
    assert board(database_url) == [(ANONYMOUS, 1, None)]
    assert solution_ids(api) == [second]
    assert api.get(f"/api/v1/solutions/{first}").status_code == 404

    assert hide(False) == 1
    assert board(database_url) == [(ANONYMOUS, 1, None)]
    assert set(solution_ids(api)) == {first, second}
    assert api.get(f"/api/v1/solutions/{first}").json()["placement"] is None


def test_the_service_user_is_not_moderated(api: TestClient, database_url: str) -> None:
    sign_in(api, database_url, "root", role="admin")
    root = staff(database_url, "root")
    with pytest.raises(ModerationRefusedError) as hiding:
        moderate(
            database_url,
            lambda moderation: moderation.hide_users(
                root, [DELETED_USER_ID], hidden=True, reason="x"
            ),
        )
    assert hiding.value.refusal == "service_target"
    with pytest.raises(ModerationRefusedError) as role:
        moderate(
            database_url,
            lambda moderation: moderation.set_role(root, DELETED_USER_ID, "admin", "x"),
        )
    assert role.value.refusal == "service_target"


def test_the_service_user_is_not_an_author_of_the_problem_stats(
    api: TestClient, database_url: str
) -> None:
    """It stands for several people, none known: as before, a deleted account does not count."""
    ada = sign_in(api, database_url, nick="ada")
    check(api, database_url, accepted(0.5, 500, "n1:ada"))
    sign_in(api, database_url, nick="eve")
    check(api, database_url, accepted(0.6, 500, "n1:eve"))
    assert purge(database_url, ada.id) == 1

    async def scenario(database: Database) -> tuple[int, int]:
        await ProblemStatsRefresh(database)()
        async with database.sessions() as session:
            found = (
                await session.execute(
                    select(ProblemStats.authors, ProblemStats.accepted_authors)
                    .join(Problem, Problem.id == ProblemStats.problem_id)
                    .where(Problem.slug == "mux4")
                )
            ).one()
            return found[0], found[1]

    assert run(database_url, scenario) == (1, 1)
