"""Minimal moderation (T3.12: FR-ADM-02 in part, FR-ADM-03): a hidden solution or user leaves the
leaderboards and public pages, showing them again brings them back; every action is logged with
its reason. The admin panel `/admin` lets in staff only and changes nothing without a form from the
site's own origin."""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
import test_leaderboard_ranking as ranking
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_ingest import run
from test_leaderboard_ranking import accepted, board, check, signed_in
from test_sessions import sign_in

from apparatica.admin.models import ModerationLog
from apparatica.admin.moderation import Moderation, ModerationRefusedError, Staff
from apparatica.auth.models import User
from apparatica.auth.sessions import COOKIE as SESSION_COOKIE
from apparatica.core.db import Database
from apparatica.submissions.models import Submission
from conftest import RATING

database_url = ranking.database_url
api = ranking.api

SOLUTIONS = "/api/v1/problems/mux4/solutions"
RATING_URL = "/api/v1/leaderboard"
ORIGIN = {"Origin": "http://testserver"}


def staff(database_url: str, nick: str) -> Staff:
    """The account of a moderator or an administrator by nick."""

    async def scenario(database: Database) -> Staff:
        async with database.sessions() as session:
            user = await session.scalar(select(User).where(User.nick == nick))
            assert user is not None
            return Staff(user.id, user.nick, user.role)  # type: ignore[arg-type]

    return run(database_url, scenario)


def moderate[T](database_url: str, act: Callable[[Moderation], Awaitable[T]]) -> T:
    async def scenario(database: Database) -> T:
        return await act(Moderation(database, RATING))

    return run(database_url, scenario)


def user_id(database_url: str, nick: str) -> uuid.UUID:
    async def scenario(database: Database) -> uuid.UUID:
        async with database.sessions() as session:
            found = await session.scalar(select(User.id).where(User.nick == nick))
            assert found is not None
            return found

    return run(database_url, scenario)


def journal(database_url: str) -> list[tuple[str | None, str, str, str, str, Any]]:
    """(nick of the actor, action, target type, target id, reason, details), oldest first."""

    async def scenario(database: Database) -> list[tuple[str | None, str, str, str, str, Any]]:
        async with database.sessions() as session:
            rows = await session.execute(
                select(
                    User.nick,
                    ModerationLog.action,
                    ModerationLog.target_type,
                    ModerationLog.target_id,
                    ModerationLog.reason,
                    ModerationLog.details,
                )
                .outerjoin(User, User.id == ModerationLog.actor_id)
                .order_by(ModerationLog.created_at, ModerationLog.id)
            )
            return [tuple(row) for row in rows]

    return run(database_url, scenario)


def solution_ids(api: TestClient) -> list[str]:
    response = api.get(SOLUTIONS)
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


def rating_nicks(api: TestClient) -> list[str]:
    response = api.get(RATING_URL)
    assert response.status_code == 200, response.text
    return [row["user"]["nick"] for row in response.json()["items"]]


def test_a_hidden_solution_hands_the_entry_to_the_next_best(
    api: TestClient, database_url: str
) -> None:
    """FR-ADM-03: the hidden best Submit of ada leaves the leaderboard, the public solutions and
    its page; her next best Submit takes the entry. Showing it again restores the place."""
    ada = signed_in(api, database_url, "ada")
    best, _ = check(api, database_url, accepted(0.5, 500, "n1:a"))
    worse, _ = check(api, database_url, accepted(0.7, 500, "n1:b"))
    signed_in(api, database_url, "bob")
    bob, _ = check(api, database_url, accepted(0.6, 500, "n1:bob"))
    sign_in(api, database_url, "mod", role="moderator")
    mod = staff(database_url, "mod")
    assert board(database_url) == [("ada", 1, None), ("bob", 2, None)]

    hidden = moderate(
        database_url,
        lambda moderation: moderation.hide_submissions(
            mod, [uuid.UUID(best)], hidden=True, reason="copied"
        ),
    )
    assert hidden == 1
    assert board(database_url) == [("bob", 1, None), ("ada", 2, None)]
    assert set(solution_ids(api)) == {worse, bob}
    assert api.get(f"/api/v1/solutions/{best}").status_code == 404  # staff too
    api.cookies.set(SESSION_COOKIE, ada)
    mine = api.get(f"/api/v1/submissions/{best}").json()
    assert (mine["public"], mine["leaderboard"]) == (False, None)
    assert api.get(f"/api/v1/submissions/{worse}").json()["leaderboard"]["rank"] == 2
    assert api.get("/api/v1/users/ada").json()["solutions"] == 1

    again = moderate(
        database_url,
        lambda moderation: moderation.hide_submissions(
            mod, [uuid.UUID(best)], hidden=True, reason="twice"
        ),
    )
    assert again == 0  # nothing changed, nothing logged
    moderate(
        database_url,
        lambda moderation: moderation.hide_submissions(
            mod, [uuid.UUID(best)], hidden=False, reason="not a copy"
        ),
    )
    assert board(database_url) == [("ada", 1, None), ("bob", 2, None)]
    assert len(solution_ids(api)) == 3
    assert journal(database_url) == [
        ("mod", "hide", "submission", best, "copied", None),
        ("mod", "unhide", "submission", best, "not a copy", None),
    ]


def test_a_hidden_user_leaves_public_pages(api: TestClient, database_url: str) -> None:
    """FR-ADM-03: a hidden user has no profile, solutions, entries or points, and a new Submit
    does not rank; the user still signs in and solves. Shown again, the best Submit ranks."""
    ada = signed_in(api, database_url, "ada")
    check(api, database_url, accepted(0.7, 500, "n1:a"))
    signed_in(api, database_url, "bob")
    check(api, database_url, accepted(0.6, 500, "n1:bob"))
    sign_in(api, database_url, "mod", role="moderator")
    mod = staff(database_url, "mod")
    assert rating_nicks(api) == ["bob", "ada"]

    ada_id = user_id(database_url, "ada")
    changed = moderate(
        database_url,
        lambda moderation: moderation.hide_users(mod, [ada_id], hidden=True, reason="spam"),
    )
    assert changed == 1
    assert board(database_url) == [("bob", 1, None)]
    assert rating_nicks(api) == ["bob"]
    assert [item["author"]["nick"] for item in api.get(SOLUTIONS).json()["items"]] == ["bob"]
    assert api.get("/api/v1/users/ada").status_code == 404
    assert api.get("/api/v1/users/ada/solutions").status_code == 404

    api.cookies.set(SESSION_COOKIE, ada)
    assert api.get("/api/v1/me").status_code == 200
    better, event = check(api, database_url, accepted(0.5, 500, "n1:c"))
    assert event is not None
    assert event.leaderboard is None
    assert board(database_url) == [("bob", 1, None)]

    moderate(
        database_url,
        lambda moderation: moderation.hide_users(mod, [ada_id], hidden=False, reason="appeal"),
    )
    assert board(database_url) == [("ada", 1, None), ("bob", 2, None)]
    assert api.get(f"/api/v1/submissions/{better}").json()["leaderboard"]["is_best"] is True
    assert rating_nicks(api) == ["ada", "bob"]
    assert [entry[1:3] for entry in journal(database_url)] == [
        ("hide", "user"),
        ("unhide", "user"),
    ]


def test_staff_is_not_hidden_and_roles_are_for_administrators(
    api: TestClient, database_url: str
) -> None:
    sign_in(api, database_url, "mod", role="moderator")
    sign_in(api, database_url, "root", role="admin")
    sign_in(api, database_url, "ada")
    mod, root = staff(database_url, "mod"), staff(database_url, "root")
    ada = user_id(database_url, "ada")

    def refused(act: Callable[[Moderation], Awaitable[Any]]) -> str:
        with pytest.raises(ModerationRefusedError) as error:
            moderate(database_url, act)
        return error.value.refusal

    assert refused(lambda m: m.hide_users(root, [mod.user_id], hidden=True, reason="x")) == (
        "staff_target"
    )
    assert refused(lambda m: m.set_role(mod, ada, "author", "x")) == "not_admin"
    assert refused(lambda m: m.set_role(root, root.user_id, "user", "x")) == "own_role"
    assert moderate(database_url, lambda m: m.set_role(root, ada, "moderator", "helps"))
    assert not moderate(database_url, lambda m: m.set_role(root, ada, "moderator", "again"))
    assert journal(database_url) == [
        ("root", "set_role", "user", str(ada), "helps", {"from": "user", "to": "moderator"})
    ]
    moderate(database_url, lambda m: m.set_role(root, ada, "user", "back"))
    moderate(database_url, lambda m: m.hide_users(root, [ada], hidden=True, reason="spam"))
    assert refused(lambda m: m.set_role(root, ada, "admin", "x")) == "hidden_staff"


def hidden_of(database_url: str, model: type[User | Submission], row_id: Any) -> bool:
    async def scenario(database: Database) -> bool:
        async with database.sessions() as session:
            found = await session.scalar(select(model.is_hidden).where(model.id == row_id))
            assert found is not None
            return found

    return run(database_url, scenario)


def test_the_panel_is_for_staff(api: TestClient, database_url: str) -> None:
    """FR-ADM-02: no session — to the login page and back; another role — 403."""
    response = api.get("/admin/user/list?page=2", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=/admin/user/list%3Fpage%3D2"
    sign_in(api, database_url, "ada")
    assert api.get("/admin/").status_code == 403
    assert api.get("/admin/statics/css/main.css").status_code == 403
    sign_in(api, database_url, "mod", role="moderator")
    for path in ("/admin/", "/admin/user/list", "/admin/submission/list"):
        assert api.get(path).status_code == 200, path
    assert "ada" in api.get("/admin/user/list").text
    assert api.get("/admin/user/create").status_code == 403  # read-only
    assert api.get("/admin/user/export/csv").status_code == 403


def test_hiding_through_the_panel(api: TestClient, database_url: str) -> None:
    """A moderator hides a user and a solution with a reason; the form passes only from the
    origin of the site; roles are for an administrator."""
    signed_in(api, database_url, "ada")
    solution, _ = check(api, database_url, accepted(0.5, 500, "n1:a<b>"))
    ada = user_id(database_url, "ada")
    sign_in(api, database_url, "mod", role="moderator")

    action = api.get(f"/admin/user/action/hide?pks={ada}", follow_redirects=False)
    assert action.status_code == 303
    form_url = action.headers["location"]
    assert form_url.endswith(f"/admin/user/moderate?action=hide&pks={ada}")
    form = api.get(form_url)
    assert form.status_code == 200
    assert "ada" in form.text
    assert "Причина" in form.text

    fields = {"action": "hide", "pks": str(ada), "reason": "spam"}
    no_origin = api.post("/admin/user/moderate", data=fields, follow_redirects=False)
    assert (no_origin.status_code, no_origin.json()["code"]) == (403, "CSRF_FAILED")
    other = api.post(
        "/admin/user/moderate",
        data=fields,
        headers={"Origin": "https://evil.example"},
        follow_redirects=False,
    )
    assert other.status_code == 403
    empty = api.post("/admin/user/moderate", data={**fields, "reason": " "}, headers=ORIGIN)
    assert empty.status_code == 400
    assert "Укажите причину" in empty.text
    assert hidden_of(database_url, User, ada) is False

    done = api.post("/admin/user/moderate", data=fields, headers=ORIGIN, follow_redirects=False)
    assert done.status_code == 303
    assert done.headers["location"].endswith(f"/admin/user/details/{ada}")
    assert hidden_of(database_url, User, ada) is True

    shown = api.post(
        "/admin/submission/moderate",
        data={"action": "hide", "pks": solution, "reason": "copied"},
        headers=ORIGIN,
        follow_redirects=False,
    )
    assert shown.status_code == 303
    assert hidden_of(database_url, Submission, uuid.UUID(solution)) is True
    details = api.get(f"/admin/submission/details/{solution}")
    assert "n1:a&lt;b&gt;" in details.text  # AST hash, escaped
    log = api.get("/admin/moderation-log/list")
    assert log.status_code == 200
    assert "copied" in log.text
    assert "spam" in log.text

    role = {"action": "role", "pks": str(ada), "role": "author", "reason": "writes"}
    assert api.post("/admin/user/moderate", data=role, headers=ORIGIN).status_code == 400
    staff_target = api.post(
        "/admin/user/moderate",
        data={**fields, "pks": str(staff(database_url, "mod").user_id)},
        headers=ORIGIN,
    )
    assert staff_target.status_code == 400
    assert "сначала снимите роль" in staff_target.text

    sign_in(api, database_url, "root", role="admin")
    assert api.get(f"/admin/user/moderate?action=role&pks={ada}").status_code == 200
    changed = api.post("/admin/user/moderate", data=role, headers=ORIGIN, follow_redirects=False)
    assert changed.status_code == 303
    assert [entry[:3] for entry in journal(database_url)] == [
        ("mod", "hide", "user"),
        ("mod", "hide", "submission"),
        ("root", "set_role", "user"),
    ]
