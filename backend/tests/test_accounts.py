"""The own account (FR-AUTH-02): the nick, changed once in 30 days, and the display name."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from test_sessions import run, sign_in

from apparatica.auth.accounts import NICK_CHANGE_EVERY
from apparatica.auth.models import User
from apparatica.auth.sessions import COOKIE
from apparatica.core.db import Database
from apparatica.core.settings import Settings
from apparatica.main import create_app
from conftest import CONFIG_DIR, ApiClient


@pytest.fixture
def api(database_url: str) -> Iterator[TestClient]:
    settings = Settings(
        environment="test", database_url=database_url, config_dir=CONFIG_DIR, cookie_secure=False
    )
    with ApiClient(create_app(settings), raise_server_exceptions=False) as client:
        yield client


def changed_nick_at(database_url: str, user: User, when: datetime) -> None:
    async def scenario(database: Database) -> None:
        async with database.sessions.begin() as session:
            await session.execute(
                update(User).where(User.id == user.id).values(nick_changed_at=when)
            )

    run(database_url, scenario)


def test_changes_need_a_session(client: TestClient) -> None:
    response = client.patch("/api/v1/me", json={"nick": "grace"})
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_the_first_change_of_the_nick_is_at_once_and_the_next_in_30_days(
    api: TestClient, database_url: str
) -> None:
    sign_in(api, database_url, "user-k3f9qz")
    assert api.get("/api/v1/me").json()["nick_change_available_at"] is None

    before = datetime.now(UTC)
    response = api.patch("/api/v1/me", json={"nick": "ada"})
    assert response.status_code == 200, response.text
    changed = response.json()
    assert changed["nick"] == "ada"
    available_at = datetime.fromisoformat(changed["nick_change_available_at"])
    assert before + NICK_CHANGE_EVERY <= available_at <= datetime.now(UTC) + NICK_CHANGE_EVERY
    assert api.get("/api/v1/me").json() == changed

    refused = api.patch("/api/v1/me", json={"nick": "lovelace"})
    assert refused.status_code == 409
    assert refused.json()["code"] == "NICK_CHANGE_TOO_SOON"
    assert datetime.fromisoformat(refused.json()["params"]["available_at"]) == available_at
    # The same nick is no change; the name changes as before.
    same = api.patch("/api/v1/me", json={"nick": "ada", "display_name": "Ada"})
    assert same.status_code == 200
    assert same.json()["display_name"] == "Ada"


def test_the_nick_changes_again_after_30_days(api: TestClient, database_url: str) -> None:
    ada = sign_in(api, database_url, "ada")
    changed_nick_at(database_url, ada, datetime.now(UTC) - NICK_CHANGE_EVERY)
    assert api.get("/api/v1/me").json()["nick_change_available_at"] is None
    response = api.patch("/api/v1/me", json={"nick": "lovelace"})
    assert response.status_code == 200
    assert response.json()["nick"] == "lovelace"

    changed_nick_at(database_url, ada, datetime.now(UTC) - timedelta(days=29))
    assert api.patch("/api/v1/me", json={"nick": "ada"}).status_code == 409


def test_a_taken_nick_is_refused_and_a_released_one_is_free(
    api: TestClient, database_url: str
) -> None:
    sign_in(api, database_url, "grace")
    grace = api.cookies[COOKIE]
    sign_in(api, database_url, "ada")

    refused = api.patch("/api/v1/me", json={"nick": "grace", "display_name": "Ada"})
    assert refused.status_code == 409
    assert refused.json()["code"] == "NICK_TAKEN"
    # A refused change changes nothing, the name included, and does not count.
    me = api.get("/api/v1/me").json()
    assert (me["nick"], me["display_name"], me["nick_change_available_at"]) == ("ada", None, None)

    ada = api.cookies[COOKIE]
    api.cookies.set(COOKIE, grace)
    assert api.patch("/api/v1/me", json={"nick": "hopper"}).status_code == 200
    api.cookies.set(COOKIE, ada)
    assert api.patch("/api/v1/me", json={"nick": "grace"}).json()["nick"] == "grace"


def test_the_display_name(api: TestClient, database_url: str) -> None:
    sign_in(api, database_url, "ada", display_name="Ada")
    response = api.patch("/api/v1/me", json={"display_name": "  Ada Lovelace "})
    assert response.json()["display_name"] == "Ada Lovelace"
    # An absent field stays; null removes the name.
    assert api.patch("/api/v1/me", json={}).json()["display_name"] == "Ada Lovelace"
    assert api.patch("/api/v1/me", json={"display_name": None}).json()["display_name"] is None
    assert api.get("/api/v1/me").json()["nick_change_available_at"] is None

    for body in ({"display_name": "   "}, {"display_name": "a" * 61}, {"nick": "Ada"}):
        refused = api.patch("/api/v1/me", json=body)
        assert refused.status_code == 422, body
        assert refused.json()["code"] == "VALIDATION_ERROR"
