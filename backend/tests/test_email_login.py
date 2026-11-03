"""Login links (FR-AUTH-05, ADR-0010): the letter, one use in 15 minutes, the account of the first
login, answers that tell nothing about accounts, limits per address, the switch of the provider."""

import asyncio
import hashlib
import json
import os
import re
import time
import urllib.request
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from test_captcha import solve
from test_sessions import add_user, consents, run
from testcontainers.core.container import DockerContainer

from apparatica.auth import accounts
from apparatica.auth.accounts import sign_up
from apparatica.auth.models import EmailToken, Identity, User
from apparatica.auth.sessions import COOKIE
from apparatica.core.db import Database
from apparatica.core.flags import Overrides
from apparatica.core.mail import Letter, SmtpMailer, SmtpServer
from apparatica.core.platform import load_platform_config
from apparatica.core.settings import Settings
from apparatica.judging.housekeeping import EmailTokenPurge
from apparatica.main import create_app
from conftest import CONFIG_DIR, ApiClient

SITE = "http://site.test"
REQUEST = "/api/v1/auth/email/request"
VERIFY = "/api/v1/auth/email/verify"
LINK = re.compile(re.escape(SITE) + r"/login/email/verify#token=([A-Za-z0-9_-]{43})\n")
DOCUMENTS = sorted(load_platform_config(CONFIG_DIR).legal.documents.versions().items())
MAILPIT_IMAGE = os.environ.get("APX_TEST_MAILPIT_IMAGE", "axllent/mailpit:v1.33.0")


@dataclass
class MemoryMailer:
    letters: list[Letter] = field(default_factory=list)
    works: bool = True

    async def send(self, letter: Letter) -> bool:
        if self.works:
            self.letters.append(letter)
        return self.works

    def token(self) -> str:
        match = LINK.search(self.letters[-1].body)
        assert match is not None, self.letters[-1].body
        return match.group(1)


def settings(database_url: str, **fields: Any) -> Settings:
    fields = {"public_base_url": SITE} | fields
    return Settings(
        environment="test",
        database_url=database_url,
        config_dir=CONFIG_DIR,
        cookie_secure=False,
        **fields,
    )


def overrides(**flags: bool) -> Overrides:
    async def load() -> Mapping[str, bool]:
        return flags

    return load


@pytest.fixture
def mailer() -> MemoryMailer:
    return MemoryMailer()


@pytest.fixture
def api(database_url: str, mailer: MemoryMailer) -> Iterator[TestClient]:
    app = create_app(settings(database_url), mailer=mailer)
    with ApiClient(app, raise_server_exceptions=False) as client:
        yield client


def sign_in(api: TestClient, mailer: MemoryMailer, email: str, **body: Any) -> Any:
    assert api.post(REQUEST, json={"email": email, **body}).status_code == 202
    return api.post(VERIFY, json={"token": mailer.token()})


def tokens(database_url: str) -> list[EmailToken]:
    async def scenario(database: Database) -> list[EmailToken]:
        async with database.sessions() as session:
            return list(await session.scalars(select(EmailToken)))

    return run(database_url, scenario)  # type: ignore[no-any-return]


def test_a_link_signs_in_and_the_first_login_creates_the_account(
    api: TestClient, mailer: MemoryMailer, database_url: str
) -> None:
    response = api.post(REQUEST, json={"email": " Ada@Example.com", "next": "/problems/mux4"})
    assert response.status_code == 422  # not an address: no spaces
    response = api.post(REQUEST, json={"email": "Ada@Example.com", "next": "/problems/mux4"})
    assert (response.status_code, response.content) == (202, b"")
    [letter] = mailer.letters
    assert (letter.to, letter.subject) == ("ada@example.com", "Вход в Apparatica")
    assert "15 минут" in letter.body
    token = mailer.token()
    # The table has the hash of the token only.
    [row] = tokens(database_url)
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert (row.email, row.next, row.used_at) == ("ada@example.com", "/problems/mux4", None)
    assert row.expires_at - row.created_at == timedelta(minutes=15)

    response = api.post(VERIFY, json={"token": token}, headers={"User-Agent": "pytest"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["created"], body["next"]) == (True, "/problems/mux4")
    user = body["user"]
    assert re.fullmatch(r"user-[a-z0-9]{6}", user["nick"])
    assert (user["email"], user["role"], user["display_name"]) == ("ada@example.com", "user", None)
    assert api.cookies.get(COOKIE)
    assert api.get("/api/v1/me").json() == user

    async def identities(database: Database) -> list[tuple[str, str, str | None]]:
        async with database.sessions() as session:
            rows = await session.execute(
                select(Identity.provider, Identity.subject, Identity.email)
            )
            return list(rows.tuples())

    assert run(database_url, identities) == [("email", "ada@example.com", "ada@example.com")]
    # The login page says that continuing accepts the documents (FR-AUTH-06).
    assert consents(database_url) == [(user["nick"], *document) for document in DOCUMENTS]


def test_a_link_works_once(api: TestClient, mailer: MemoryMailer) -> None:
    assert sign_in(api, mailer, "ada@example.com").status_code == 200
    for token in (mailer.token(), "x" * 43, "y" * 128):
        response = api.post(VERIFY, json={"token": token})
        assert (response.status_code, response.json()["code"]) == (400, "LOGIN_LINK_INVALID")
    assert api.post(VERIFY, json={"token": "x" * 129}).status_code == 422


def test_the_next_login_finds_the_account(
    api: TestClient, mailer: MemoryMailer, database_url: str
) -> None:
    first = sign_in(api, mailer, "ada@example.com").json()
    earlier = api.cookies.get(COOKIE)
    again = sign_in(api, mailer, "ADA@example.com").json()
    assert (again["created"], again["next"]) == (False, None)
    assert again["user"] == first["user"]
    assert len(consents(database_url)) == 2  # accepted by the first login only
    other = sign_in(api, mailer, "grace@example.com").json()
    assert other["created"] is True
    assert other["user"]["id"] != first["user"]["id"]
    # A login ends the session it replaces.
    api.cookies.delete(COOKIE)  # the jar keeps the cookie of the response besides a set one
    api.cookies.set(COOKIE, str(earlier))
    assert api.get("/api/v1/me").status_code == 401


def test_an_expired_link_is_refused_and_purged(
    api: TestClient, mailer: MemoryMailer, database_url: str
) -> None:
    for email in ("ada@example.com", "grace@example.com"):
        assert api.post(REQUEST, json={"email": email}).status_code == 202
    expired, live = mailer.letters
    now = datetime.now(UTC)

    async def expire(database: Database) -> None:
        async with database.sessions.begin() as session:
            await session.execute(
                update(EmailToken)
                .where(EmailToken.email == expired.to)
                .values(expires_at=now - timedelta(seconds=1))
            )

    run(database_url, expire)
    mailer.letters.remove(live)
    response = api.post(VERIFY, json={"token": mailer.token()})
    assert (response.status_code, response.json()["code"]) == (400, "LOGIN_LINK_INVALID")
    purged = run(database_url, lambda database: EmailTokenPurge(database, clock=lambda: now)())
    assert purged == 1
    assert [row.email for row in tokens(database_url)] == [live.to]


def test_the_answer_does_not_tell_whether_an_account_exists(
    api: TestClient, mailer: MemoryMailer
) -> None:
    assert sign_in(api, mailer, "ada@example.com").status_code == 200
    known = api.post(REQUEST, json={"email": "ada@example.com"})
    unknown = api.post(REQUEST, json={"email": "nobody@example.com"})
    assert (known.status_code, known.content) == (unknown.status_code, unknown.content)
    assert [letter.to for letter in mailer.letters[-2:]] == [
        "ada@example.com",
        "nobody@example.com",
    ]


def test_a_failed_letter_answers_the_same(database_url: str) -> None:
    mailer = MemoryMailer(works=False)
    app = create_app(settings(database_url), mailer=mailer)
    with ApiClient(app, raise_server_exceptions=False) as api:
        assert api.post(REQUEST, json={"email": "ada@example.com"}).status_code == 202


def test_links_to_one_address_are_limited(api: TestClient, mailer: MemoryMailer) -> None:
    window = api.app.state.platform.rate_limits.logins_per_email  # type: ignore[attr-defined]
    for _ in range(window.limit):
        assert api.post(REQUEST, json={"email": "ada@example.com"}).status_code == 202
    response = api.post(REQUEST, json={"email": "ADA@example.com"})
    assert response.status_code == 429
    params = response.json()["params"]
    assert (params["quota"], params["limit"], params["window_s"]) == (
        "logins",
        window.limit,
        window.window_s,
    )
    assert len(mailer.letters) == window.limit
    assert api.post(REQUEST, json={"email": "grace@example.com"}).status_code == 202


def test_email_login_needs_smtp_and_its_flag(database_url: str, client: TestClient) -> None:
    # `client` has no SMTP server.
    assert client.get("/api/v1/config").json()["auth_providers"] == []
    for path, body in ((REQUEST, {"email": "ada@example.com"}), (VERIFY, {"token": "x" * 43})):
        response = client.post(path, json=body)
        assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")

    for flags, providers in (
        ({}, [{"key": "email", "title": "Email", "kind": "email"}]),
        ({"auth_email": False}, []),
    ):
        app = create_app(
            settings(database_url), flag_overrides=overrides(**flags), mailer=MemoryMailer()
        )
        with ApiClient(app, raise_server_exceptions=False) as api:
            assert api.get("/api/v1/config").json()["auth_providers"] == providers
            status = api.post(REQUEST, json={"email": "ada@example.com"}).status_code
            assert status == (202 if providers else 404)

    with pytest.raises(RuntimeError, match="APX_PUBLIC_BASE_URL"):
        create_app(settings(database_url, public_base_url=None), mailer=MemoryMailer())


def test_the_captcha_flag_asks_for_a_captcha(database_url: str) -> None:
    mailer = MemoryMailer()
    app = create_app(settings(database_url), flag_overrides=overrides(captcha=True), mailer=mailer)
    with ApiClient(app, raise_server_exceptions=False) as api:
        response = api.post(REQUEST, json={"email": "ada@example.com"})
        assert (response.status_code, response.json()["params"]["reason"]) == (428, "always")
        challenge = api.get("/api/v1/captcha/challenge").json()
        body = {"email": "ada@example.com", "captcha": solve(challenge)}
        assert api.post(REQUEST, json=body).status_code == 202
        assert api.post(REQUEST, json=body).status_code == 428  # a solution works once
        assert len(mailer.letters) == 1


def test_a_taken_nick_is_drawn_again(database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    nicks = iter(["user-aaaaaa", "user-aaaaaa", "user-bbbbbb"])
    monkeypatch.setattr(accounts, "random_nick", lambda: next(nicks))

    async def scenario(database: Database) -> tuple[str, str]:
        await add_user(database, "user-aaaaaa")
        async with database.sessions.begin() as session:
            first, created = await sign_up(
                session, "email", "ada@example.com", email=None, documents={}
            )
            assert created
        async with database.sessions.begin() as session:
            again, created = await sign_up(
                session, "email", "ada@example.com", email=None, documents={}
            )
            assert not created
            assert again.id == first.id
            count = len((await session.scalars(select(User))).all())
        assert count == 2
        return first.nick, again.nick

    assert run(database_url, scenario) == ("user-bbbbbb", "user-bbbbbb")


def test_smtp_urls() -> None:
    server = SmtpServer.parse("smtps://apparatica%40mail:p%3Ass@smtp.example.com")
    assert server == SmtpServer("smtps", "smtp.example.com", 465, "apparatica@mail", "p:ss")
    assert SmtpServer.parse("smtp+starttls://smtp.example.com").port == 587
    assert SmtpServer.parse("smtp://mailpit:1025") == SmtpServer(
        "smtp", "mailpit", 1025, None, None
    )
    for url in ("http://smtp.example.com", "smtp://", "mailpit:1025"):
        with pytest.raises(ValueError, match="APX_SMTP_URL"):
            SmtpServer.parse(url)


@pytest.fixture(scope="module")
def mailpit() -> Iterator[tuple[str, str]]:
    """The SMTP URL and the HTTP API of a Mailpit server."""
    try:
        container = DockerContainer(MAILPIT_IMAGE).with_exposed_ports(1025, 8025).start()
    except Exception as error:
        if os.environ.get("CI"):
            raise
        pytest.skip(f"Mailpit tests need Docker: {error!r}")
    try:
        host = container.get_container_host_ip()
        web = f"http://{host}:{container.get_exposed_port(8025)}"
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{web}/readyz", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        yield f"smtp://{host}:{container.get_exposed_port(1025)}", web
    finally:
        container.stop()


def test_letters_go_over_smtp(mailpit: tuple[str, str]) -> None:
    url, web = mailpit
    mailer = SmtpMailer(url, "Apparatica <noreply@apparatica.test>", timeout_s=5)
    letter = Letter("login-link", "ada@example.com", "Вход в Apparatica", "Ссылка: …\n")
    assert asyncio.run(mailer.send(letter)) is True
    with urllib.request.urlopen(f"{web}/api/v1/messages", timeout=5) as response:
        [message] = json.load(response)["messages"]
    assert message["Subject"] == "Вход в Apparatica"
    assert [to["Address"] for to in message["To"]] == ["ada@example.com"]
    assert message["From"]["Address"] == "noreply@apparatica.test"

    closed = SmtpMailer("smtp://127.0.0.1:9", "noreply@apparatica.test", timeout_s=1)
    assert asyncio.run(closed.send(letter)) is False
