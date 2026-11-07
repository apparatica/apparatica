"""Roles (FR-AUTH-07) and the rate limits of signed-in users and of logins (NFR-SEC-06)."""

import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_sessions import run, sign_in

from apparatica.admin.cli import main
from apparatica.admin.models import ModerationLog
from apparatica.auth.models import User
from apparatica.auth.roles import require_role
from apparatica.core.db import Database
from apparatica.core.settings import Settings, get_settings
from apparatica.main import create_app
from conftest import CONFIG_DIR, ApiClient

LIMITS = (
    "requests_per_ip: {limit: 100, window_s: 60}\n"
    "requests_per_author: {limit: 2, window_s: 60}\n"
    "drafts_per_user: {limit: 100, window_s: 60}\n"
    "checks_per_ip: {limit: 100, window_s: 3600}\n"
    "logins_per_ip: {limit: 2, window_s: 600}\n"
    "logins_per_email: {limit: 5, window_s: 3600}\n"
    "captcha:\n"
    "  per_guest: {limit: 3, window_s: 60}\n"
    "  per_ip: {limit: 10, window_s: 60}\n"
    "  max_number: 1000\n"
    "  expires_s: 600\n"
)


def app_client(database_url: str, config_dir: Path = CONFIG_DIR, **fields: Any) -> TestClient:
    settings = Settings(
        environment="test",
        database_url=database_url,
        config_dir=config_dir,
        cookie_secure=False,
        **fields,
    )
    app = create_app(settings)
    router = APIRouter()

    @router.get("/moderated")
    async def moderated(user: Annotated[User, Depends(require_role("moderator"))]) -> str:
        return user.nick

    app.include_router(router, prefix="/api/v1/test")
    return ApiClient(app, raise_server_exceptions=False)


@pytest.fixture
def limits(tmp_path: Path) -> Path:
    for name in ("difficulties.yaml", "catalog.yaml", "limits.yaml", "legal.yaml", "rating.yaml"):
        shutil.copy(CONFIG_DIR / name, tmp_path / name)
    (tmp_path / "rate-limits.yaml").write_text(LIMITS, encoding="utf-8")
    return tmp_path


@pytest.fixture
def api(database_url: str) -> Iterator[TestClient]:
    with app_client(database_url) as client:
        yield client


def test_routes_for_roles(api: TestClient, database_url: str) -> None:
    assert api.get("/api/v1/test/moderated").json()["code"] == "UNAUTHENTICATED"
    sign_in(api, database_url, "ada")
    forbidden = api.get("/api/v1/test/moderated")
    assert (forbidden.status_code, forbidden.json()["code"]) == (403, "FORBIDDEN")
    for role in ("moderator", "admin"):  # an administrator may do everything
        sign_in(api, database_url, role, role=role)
        assert api.get("/api/v1/test/moderated").json() == role


def test_the_role_is_read_at_each_request(
    api: TestClient, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(api, database_url, "ada")
    assert api.get("/api/v1/test/moderated").status_code == 403
    monkeypatch.setenv("APX_DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        assert main(["users", "set-role", "Ada", "moderator"]) == 0  # nicks ignore case
        assert main(["users", "set-role", "bob", "moderator"]) == 1
        with pytest.raises(SystemExit):
            main(["users", "set-role", "ada", "root"])
    finally:
        get_settings.cache_clear()
    assert api.get("/api/v1/test/moderated").json() == "ada"

    async def roles(database: Database) -> dict[str, str]:
        async with database.sessions() as session:
            return dict((await session.execute(select(User.nick, User.role))).tuples().all())

    assert run(database_url, roles) == {"ada": "moderator"}

    async def journal(database: Database) -> list[tuple[Any, ...]]:
        async with database.sessions() as session:
            rows = await session.execute(
                select(
                    ModerationLog.actor_id,
                    ModerationLog.action,
                    ModerationLog.reason,
                    ModerationLog.details,
                )
            )
            return [tuple(row) for row in rows]

    # Logged without an actor (FR-ADM-03).
    assert run(database_url, journal) == [
        (None, "set_role", "apparatica-admin users set-role", {"from": "user", "to": "moderator"})
    ]


def test_requests_of_a_user_are_limited_per_user(database_url: str, limits: Path) -> None:
    with app_client(database_url, limits) as client:
        sign_in(client, database_url, "ada")
        logout_all = "/api/v1/auth/logout-all"
        assert client.patch("/api/v1/me", json={}).status_code == 200
        assert client.post("/api/v1/me/restore").status_code == 200
        limited = client.post(logout_all)
        assert (limited.status_code, limited.json()["params"]["quota"]) == (429, "requests")
        sign_in(client, database_url, "bob")  # another user of the address
        assert client.post(logout_all).status_code == 204


def test_logins_are_limited_per_address(limits: Path) -> None:
    def login(client: TestClient) -> Any:
        return client.get("/api/v1/auth/github/login", follow_redirects=False)

    github = {
        "public_base_url": "http://site.test",
        "github_client_id": "client-id",
        "github_client_secret": "client-secret",
    }
    with app_client("sqlite+aiosqlite:///:memory:", limits, **github) as client:
        assert login(client).headers["location"].startswith("https://github.com/")
        link = client.post("/api/v1/auth/email/request", json={"email": "ada@example.com"})
        assert link.status_code == 404  # no SMTP: no email login
        limited = client.post("/api/v1/auth/email/verify", json={"token": "t" * 43})
        assert limited.status_code == 429
        params = limited.json()["params"]
        assert (params["quota"], params["limit"], params["window_s"]) == ("logins", 2, 600)
        assert 0 < int(limited.headers["retry-after"]) <= 600
        # A login with a provider is a page: its limit is a page too.
        redirect = login(client)
        assert (redirect.status_code, redirect.headers["location"]) == (
            302,
            "/login?error=rate_limited",
        )
