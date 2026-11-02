"""Accounts and sessions (FR-AUTH-04, ADR-0010): the tables, the session cookie, renewal by use,
logout on one and on every device, the cache of sessions and the purge of expired ones."""

import asyncio
import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import redis.asyncio
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from apparatica.auth.models import Identity, User, UserSession
from apparatica.auth.sessions import CACHE_TTL_S, COOKIE, RENEW_EVERY, Sessions
from apparatica.core.db import Database
from apparatica.core.ids import uuid7
from apparatica.core.settings import Settings
from apparatica.judging.housekeeping import SessionPurge
from apparatica.main import create_app
from conftest import CONFIG_DIR, ApiClient

TTL = timedelta(days=30)
NOW = datetime(2026, 11, 2, 12, tzinfo=UTC)


def run(url: str, scenario: Any) -> Any:
    async def main() -> Any:
        database = Database(url)
        try:
            return await scenario(database)
        finally:
            await database.dispose()

    return asyncio.run(main())


def account(nick: str = "ada", **fields: Any) -> User:
    return User(id=uuid7(), nick=nick, **fields)


async def add_user(database: Database, nick: str = "ada", **fields: Any) -> User:
    row = account(nick, **fields)
    async with database.sessions.begin() as session:
        session.add(row)
    return row


async def start(sessions: Sessions, database: Database, user: User) -> str:
    async with database.sessions.begin() as session:
        return await sessions.start(session, user.id, "pytest")


async def rows(database: Database) -> list[UserSession]:
    async with database.sessions() as session:
        return list(await session.scalars(select(UserSession).order_by(UserSession.created_at)))


def clock(value: datetime) -> Any:
    return lambda: value


@pytest.fixture
def api(database_url: str) -> Iterator[TestClient]:
    # Plain HTTP: the test client keeps and sends back the cookies it gets.
    settings = Settings(
        environment="test", database_url=database_url, config_dir=CONFIG_DIR, cookie_secure=False
    )
    with ApiClient(create_app(settings), raise_server_exceptions=False) as client:
        yield client


def sign_in(api: TestClient, database_url: str, nick: str = "ada", **fields: Any) -> User:
    """Add a user and give the client a session of them."""
    sessions: Sessions = api.app.state.sessions  # type: ignore[attr-defined]

    async def scenario(database: Database) -> tuple[User, str]:
        user = await add_user(database, nick, **fields)
        return user, await start(sessions, database, user)

    user: User
    user, token = run(database_url, scenario)
    api.cookies.set(COOKIE, token)
    return user


def cookie_header(response: Any) -> str:
    [header] = [
        value for value in response.headers.get_list("set-cookie") if value.startswith(COOKIE)
    ]
    return str(header)


def test_routes_of_signed_in_users_need_a_session(client: TestClient) -> None:
    for method, path in (("GET", "/api/v1/me"), ("POST", "/api/v1/auth/logout-all")):
        response = client.request(method, path)
        assert response.status_code == 401
        assert response.json()["code"] == "UNAUTHENTICATED"
    # Not a token of ours: refused without a lookup (the SQLite of `client` has no tables).
    client.cookies.set(COOKIE, "x" * 129)
    assert client.get("/api/v1/me").status_code == 401


def test_logout_without_a_session_clears_the_cookie(client: TestClient) -> None:
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert "Max-Age=0" in cookie_header(response)


def test_the_account_tables(database_url: str) -> None:
    async def rejected(database: Database, *rows: Any) -> None:
        with pytest.raises(IntegrityError):
            async with database.sessions.begin() as session:
                session.add_all(rows)

    async def scenario(database: Database) -> None:
        ada = await add_user(database, email="Ada@Example.com")
        for nick in ("Ada", "ab", "a" * 25, "ada lovelace"):
            await rejected(database, account(nick))
        await rejected(database, account("ada"))  # nicks are unique
        await rejected(database, account("bob", role="root"))
        await rejected(
            database,
            UserSession(id_hash="token", user_id=ada.id, expires_at=NOW, last_seen_at=NOW),
        )
        github = Identity(id=uuid7(), user_id=ada.id, provider="github", subject="1")
        async with database.sessions.begin() as session:
            session.add(github)
        await start(Sessions(database, None, ttl_s=60, secure=True), database, ada)
        bob = await add_user(database, "bob")
        await rejected(database, Identity(user_id=bob.id, provider="github", subject="1"))

        async with database.sessions() as session:
            found = await session.scalar(select(User.nick).where(User.email == "ada@example.com"))
            assert found == "ada"  # addresses compare without case
            assert (await session.get_one(User, ada.id)).role == "user"
        async with database.sessions.begin() as session:
            await session.execute(text("DELETE FROM users WHERE nick = 'ada'"))
        async with database.sessions() as session:  # identities and sessions go with the user
            assert await session.scalar(select(func.count()).select_from(Identity)) == 0
            assert await session.scalar(select(func.count()).select_from(UserSession)) == 0

    run(database_url, scenario)


def test_a_session_signs_the_user_in(api: TestClient, database_url: str) -> None:
    user = sign_in(api, database_url, email="ada@example.com", display_name="Ada")
    response = api.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json() == {
        "id": str(user.id),
        "nick": "ada",
        "display_name": "Ada",
        "avatar_url": None,
        "email": "ada@example.com",
        "role": "user",
        "created_at": response.json()["created_at"],
        "nick_change_available_at": None,
        "delete_at": None,
    }
    assert "set-cookie" not in response.headers  # just started: nothing to renew

    [row] = run(database_url, rows)
    token = api.cookies[COOKIE]
    assert row.id_hash == hashlib.sha256(token.encode()).hexdigest()  # never the token itself
    assert row.user_agent == "pytest"
    assert row.expires_at - row.created_at == TTL


def test_a_used_session_is_renewed(api: TestClient, database_url: str) -> None:
    sign_in(api, database_url)
    stale = datetime.now(UTC) - RENEW_EVERY - timedelta(minutes=1)

    async def age(database: Database) -> None:
        async with database.sessions.begin() as session:
            await session.execute(
                update(UserSession).values(last_seen_at=stale, expires_at=stale + TTL)
            )

    run(database_url, age)
    response = api.get("/api/v1/me")
    assert response.status_code == 200
    header = cookie_header(response)
    assert f"Max-Age={int(TTL.total_seconds())}" in header
    assert "HttpOnly" in header
    assert "SameSite=lax" in header
    assert "Path=/" in header
    [row] = run(database_url, rows)
    assert row.last_seen_at > stale + RENEW_EVERY
    assert row.expires_at == row.last_seen_at + TTL
    assert "set-cookie" not in api.get("/api/v1/me").headers  # renewed an hour at most


def test_an_expired_or_unknown_session_signs_nobody_in(api: TestClient, database_url: str) -> None:
    sign_in(api, database_url)

    async def expire(database: Database) -> None:
        async with database.sessions.begin() as session:
            await session.execute(update(UserSession).values(expires_at=datetime.now(UTC)))

    run(database_url, expire)
    assert api.get("/api/v1/me").status_code == 401
    api.cookies.set(COOKIE, "unknown-token")
    assert api.get("/api/v1/me").status_code == 401


def test_logout_ends_the_session(api: TestClient, database_url: str) -> None:
    user = sign_in(api, database_url)
    sessions: Sessions = api.app.state.sessions  # type: ignore[attr-defined]
    other = run(database_url, lambda database: start(sessions, database, user))
    token = api.cookies[COOKIE]

    response = api.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert "Max-Age=0" in cookie_header(response)
    api.cookies.set(COOKIE, token)  # a copy of the cookie is no use
    assert api.get("/api/v1/me").status_code == 401
    api.cookies.set(COOKIE, other)  # the sessions on other devices stay
    assert api.get("/api/v1/me").status_code == 200


def test_logout_everywhere_ends_every_session_of_the_user(
    api: TestClient, database_url: str
) -> None:
    ada = sign_in(api, database_url)
    sessions: Sessions = api.app.state.sessions  # type: ignore[attr-defined]

    async def more(database: Database) -> str:
        await start(sessions, database, ada)
        return await start(sessions, database, await add_user(database, "bob"))

    bob = run(database_url, more)
    response = api.post("/api/v1/auth/logout-all")
    assert response.status_code == 204
    assert "Max-Age=0" in cookie_header(response)
    [left] = run(database_url, rows)
    assert left.id_hash == hashlib.sha256(bob.encode()).hexdigest()


def test_the_cache_keeps_sessions_until_they_end(database_url: str, valkey_url: str) -> None:
    async def scenario(database: Database) -> None:
        cache = redis.asyncio.Redis.from_url(valkey_url)
        try:
            sessions = Sessions(database, cache, ttl_s=86400, secure=True)
            user = await add_user(database)
            token = await start(sessions, database, user)
            key = f"session:{hashlib.sha256(token.encode()).hexdigest()}"
            found = await sessions.find(token)
            assert found is not None
            assert found.user_id == user.id
            assert 0 < await cache.ttl(key) <= CACHE_TTL_S

            # Found in the cache without the database, the way another process of the API does.
            async with database.sessions.begin() as session:
                await session.execute(text("DELETE FROM sessions"))
            assert await sessions.find(token) == found
            await sessions.end(token)
            assert await cache.exists(key) == 0
            assert await sessions.find(token) is None

            token = await start(sessions, database, user)
            assert await sessions.find(token) is not None
            await sessions.end_all(user.id)
            assert await sessions.find(token) is None
        finally:
            await cache.aclose()

    run(database_url, scenario)


def test_without_the_cache_sessions_come_from_the_database(database_url: str) -> None:
    async def scenario(database: Database) -> None:
        # Nothing listens there: every lookup misses the cache and goes on to the database.
        cache = redis.asyncio.Redis.from_url(
            "redis://127.0.0.1:1/0", socket_connect_timeout=0.2, socket_timeout=0.2
        )
        try:
            sessions = Sessions(database, cache, ttl_s=86400, secure=True)
            user = await add_user(database)
            token = await start(sessions, database, user)
            found = await sessions.find(token)
            assert found is not None
            assert found.user_id == user.id
            await sessions.end(token)
            assert await sessions.find(token) is None
        finally:
            await cache.aclose()

    run(database_url, scenario)


def test_sessions_renew_and_expire_by_the_clock(database_url: str) -> None:
    async def scenario(database: Database) -> None:
        def at(moment: datetime) -> Sessions:
            return Sessions(database, None, ttl_s=86400, secure=True, clock=clock(moment))

        token = await start(at(NOW), database, await add_user(database))

        found = await at(NOW + RENEW_EVERY / 2).find(token)
        assert found is not None
        assert not found.renewed
        assert found.expires_at == NOW + timedelta(days=1)
        later = NOW + timedelta(hours=23)
        found = await at(later).find(token)
        assert found is not None
        assert found.renewed
        assert found.expires_at == later + timedelta(days=1)
        assert await at(later + timedelta(days=1)).find(token) is None

        purge = SessionPurge(database, clock=lambda: later + timedelta(days=1))
        assert await purge() == 1
        assert await purge() == 0
        assert await rows(database) == []

    run(database_url, scenario)


def test_tokens_are_random(database_url: str) -> None:
    async def scenario(database: Database) -> set[str]:
        sessions = Sessions(database, None, ttl_s=60, secure=True)
        user = await add_user(database)
        return {await start(sessions, database, user) for _ in range(3)}

    tokens = run(database_url, scenario)
    assert len(tokens) == 3
    assert all(len(token) >= 43 for token in tokens)  # 32 random bytes
