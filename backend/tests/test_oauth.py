"""Logins with GitHub (FR-AUTH-01, ADR-0010): the redirect with state and PKCE, the callback that
creates the account, the failures that go back to the login page, the switch of the provider. GitHub
is a fake on recorded answers of its API."""

import base64
import hashlib
import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_email_login import overrides
from test_sessions import add_user, run

from apparatica.auth import oauth
from apparatica.auth.accounts import nicks
from apparatica.auth.models import Identity, User
from apparatica.auth.sessions import COOKIE
from apparatica.core.db import Database
from apparatica.core.flags import Overrides
from apparatica.core.settings import Settings
from apparatica.main import create_app
from conftest import CONFIG_DIR, ApiClient

SITE = "http://site.test"
LOGIN = "/api/v1/auth/github/login"
CALLBACK = "/api/v1/auth/github/callback"
CLIENT_ID = "Iv1.0123456789abcdef"
CLIENT_SECRET = "github-client-secret-of-the-tests"
TOKEN = "gho_16C7e42F292c6912E7710c838347Ae178B4a"

# Answers of GitHub as its documentation records them (docs.github.com: authorizing OAuth apps,
# troubleshooting token request errors, GET /user), trimmed of fields a login does not read.
TOKEN_ANSWER = {"access_token": TOKEN, "token_type": "bearer", "scope": ""}
BAD_CODE_ANSWER = {
    "error": "bad_verification_code",
    "error_description": "The code passed is incorrect or expired.",
    "error_uri": "https://docs.github.com/apps/managing-oauth-apps/troubleshooting-oauth-app-access-token-request-errors/#bad-verification-code",
}
USER_ANSWER = {
    "login": "Octocat",
    "id": 1,
    "node_id": "MDQ6VXNlcjE=",
    "avatar_url": "https://avatars.githubusercontent.com/u/1?v=4",
    "html_url": "https://github.com/octocat",
    "type": "User",
    "site_admin": False,
    "name": "monalisa octocat",
    "company": "GitHub",
    "email": "octocat@github.com",
    "created_at": "2008-01-14T04:33:35Z",
}


@dataclass
class FakeGitHub:
    """The token endpoint and GET /user of GitHub; checks the requests a login sends. A code is
    spent once, like at GitHub."""

    user: dict[str, Any] = field(default_factory=lambda: dict(USER_ANSWER))
    token_answer: dict[str, Any] = field(default_factory=lambda: dict(TOKEN_ANSWER))
    user_status: int = 200
    down: bool = False
    challenges: dict[str, str] = field(default_factory=dict)  # code → its PKCE challenge
    requests: list[str] = field(default_factory=list)

    def authorize(self, location: str, code: str = "c0de") -> str:
        """Approve the login like the user on the authorization page: the query of the callback."""
        query = {key: value for key, [value] in parse_qs(urlsplit(location).query).items()}
        assert location.startswith(oauth.GitHub.authorize_url + "?")
        assert query["code_challenge_method"] == "S256"
        self.challenges[code] = query["code_challenge"]
        return f"?code={code}&state={query['state']}"

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(f"{request.method} {request.url}")
        if self.down:
            raise httpx2.ConnectError("unreachable", request=request)
        if str(request.url) == oauth.GitHub.token_url:
            form = {key: value for key, [value] in parse_qs(request.content.decode()).items()}
            assert request.headers["accept"] == "application/json"
            assert (form["client_id"], form["client_secret"]) == (CLIENT_ID, CLIENT_SECRET)
            assert form["grant_type"] == "authorization_code"
            assert form["redirect_uri"] == SITE + CALLBACK
            challenge = self.challenges.pop(form["code"], None)
            if challenge is None:
                return httpx2.Response(200, json=BAD_CODE_ANSWER)
            digest = hashlib.sha256(form["code_verifier"].encode()).digest()
            assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == challenge
            return httpx2.Response(200, json=self.token_answer)
        if str(request.url) == oauth.GitHub.user_url:
            assert request.headers["authorization"] == f"Bearer {TOKEN}"
            if self.user_status != 200:
                return httpx2.Response(self.user_status, text="<html>unicorn</html>")
            return httpx2.Response(200, json=self.user)
        return httpx2.Response(404)


def settings(database_url: str, **fields: Any) -> Settings:
    fields = {
        "public_base_url": SITE,
        "github_client_id": CLIENT_ID,
        "github_client_secret": CLIENT_SECRET,
    } | fields
    return Settings(
        environment="test",
        database_url=database_url,
        config_dir=CONFIG_DIR,
        cookie_secure=False,
        **fields,
    )


def client(
    database_url: str, github: FakeGitHub, flags: Overrides | None = None, **fields: Any
) -> TestClient:
    app = create_app(
        settings(database_url, **fields),
        flag_overrides=flags or overrides(),
        oauth_transport=httpx2.MockTransport(github.handle),
    )
    return ApiClient(app, raise_server_exceptions=False, base_url=SITE)


@pytest.fixture
def github() -> FakeGitHub:
    return FakeGitHub()


@pytest.fixture
def api(database_url: str, github: FakeGitHub) -> Iterator[TestClient]:
    with client(database_url, github) as test_client:
        yield test_client


def sign_in(api: TestClient, github: FakeGitHub, next: str | None = None) -> httpx2.Response:
    login = api.get(LOGIN, params={"next": next} if next else None, follow_redirects=False)
    assert login.status_code == 302, login.text
    return api.get(CALLBACK + github.authorize(login.headers["location"]), follow_redirects=False)


def accounts(database_url: str) -> list[tuple[str, str | None, str | None, str, str]]:
    async def scenario(database: Database) -> list[tuple[str, str | None, str | None, str, str]]:
        async with database.sessions() as session:
            rows = await session.execute(
                select(
                    User.nick, User.display_name, User.email, Identity.provider, Identity.subject
                )
                .join(Identity)
                .order_by(User.created_at)
            )
            return list(rows.tuples())

    return run(database_url, scenario)  # type: ignore[no-any-return]


def test_a_github_login_signs_in_and_the_first_one_creates_the_account(
    api: TestClient, github: FakeGitHub, database_url: str
) -> None:
    login = api.get(LOGIN, params={"next": "/problems/mux4"}, follow_redirects=False)
    assert login.status_code == 302
    location = login.headers["location"]
    query = {key: value for key, [value] in parse_qs(urlsplit(location).query).items()}
    assert query["client_id"] == CLIENT_ID
    assert query["redirect_uri"] == SITE + CALLBACK
    assert query["response_type"] == "code"
    assert "scope" not in query  # public data only
    assert len(query["state"]) >= 43
    # The started login waits in a cookie of the callback path, not readable by scripts.
    cookie = login.headers["set-cookie"]
    assert cookie.startswith(f"{oauth.COOKIE}=")
    for attribute in (f"Path={CALLBACK}", "HttpOnly", "SameSite=lax", "Max-Age=600"):
        assert attribute in cookie
    assert github.requests == []  # the start asks GitHub nothing

    callback = api.get(CALLBACK + github.authorize(location), follow_redirects=False)
    assert (callback.status_code, callback.headers["location"]) == (302, "/problems/mux4")
    assert github.requests == [
        f"POST {oauth.GitHub.token_url}",
        f"GET {oauth.GitHub.user_url}",
    ]
    assert api.cookies.get(COOKIE)
    assert oauth.COOKIE not in api.cookies  # cleared
    me = api.get("/api/v1/me").json()
    assert (me["nick"], me["display_name"], me["email"], me["role"]) == (
        "octocat",
        "monalisa octocat",
        "octocat@github.com",
        "user",
    )
    assert me["avatar_url"] == "https://avatars.githubusercontent.com/u/1?v=4"
    assert accounts(database_url) == [
        ("octocat", "monalisa octocat", "octocat@github.com", "github", "1")
    ]


def test_the_next_login_finds_the_account_and_keeps_its_profile(
    api: TestClient, github: FakeGitHub, database_url: str
) -> None:
    first = sign_in(api, github)
    assert first.headers["location"] == "/"
    old_session = api.cookies[COOKIE]
    # The user renames the account at GitHub: the login is by id, the profile is ours now.
    github.user |= {"login": "monalisa", "name": "Mona Lisa", "email": None}
    second = sign_in(api, github)
    assert second.status_code == 302
    assert api.cookies[COOKIE] != old_session
    assert accounts(database_url) == [
        ("octocat", "monalisa octocat", "octocat@github.com", "github", "1")
    ]
    # The login replaced the session of the browser: the old one is ended.
    api.cookies.delete(COOKIE)
    api.cookies.set(COOKIE, old_session)
    assert api.get("/api/v1/me").status_code == 401


def test_a_taken_nick_gets_a_suffix_and_an_email_account_is_another_account(
    api: TestClient, github: FakeGitHub, database_url: str
) -> None:
    async def scenario(database: Database) -> None:
        await add_user(database, "octocat", email="octocat@github.com")

    run(database_url, scenario)
    assert sign_in(api, github).status_code == 302
    nick = api.get("/api/v1/me").json()["nick"]
    assert re.fullmatch(r"octocat-[a-z0-9]{4}", nick), nick

    async def count(database: Database) -> int:
        async with database.sessions() as session:
            return await session.scalar(select(func.count()).select_from(User)) or 0

    assert run(database_url, count) == 2  # accounts are not joined by email (ADR-0010)


def test_nicks_of_providers_take_the_form_of_nicks() -> None:
    def first(preferred: str | None, n: int = 1) -> list[str]:
        candidates = nicks(preferred)
        return [next(candidates) for _ in range(n)]

    assert first("Ada") == ["ada"]
    [taken, suffixed] = first("Ada", 2)
    assert taken == "ada"
    assert re.fullmatch(r"ada-[a-z0-9]{4}", suffixed)
    assert re.fullmatch(r"x-[a-z0-9]{4}", first("x")[0])  # GitHub logins may be 1 character
    long = "a-very-long-github-login-of-39-character"
    assert first(long) == [long[:24]]
    assert re.fullmatch(r"a-very-long-github-[a-z0-9]{4}", first(long, 2)[1])
    assert first("Анна Petrova")[0] == "petrova"
    for none in (None, "", "Анна"):
        assert re.fullmatch(r"user-[a-z0-9]{6}", first(none)[0])
    for nick in first("ada", 20) + first(long, 20) + first("x", 20):
        assert re.fullmatch(r"[a-z0-9_.-]{3,24}", nick)


@pytest.mark.parametrize(
    ("change", "callback", "reason"),
    [
        (None, "?code=c0de&state=forged", "invalid_state"),
        (None, "?code=c0de", "invalid_state"),
        (None, "?state={state}", "provider_error"),
        (None, "?error=access_denied&state={state}", "access_denied"),
        (None, "?error=redirect_uri_mismatch&state={state}", "provider_error"),
        ({"token_answer": BAD_CODE_ANSWER}, "", "provider_error"),
        ({"token_answer": {"token_type": "bearer"}}, "", "provider_error"),
        ({"down": True}, "", "provider_error"),
        ({"user_status": 502}, "", "provider_error"),
        ({"user": {"login": "octocat"}}, "", "provider_error"),  # no id
    ],
)
def test_a_failed_login_goes_back_to_the_login_page(
    api: TestClient,
    github: FakeGitHub,
    database_url: str,
    change: Mapping[str, Any] | None,
    callback: str,
    reason: str,
) -> None:
    for name, value in (change or {}).items():
        setattr(github, name, value)
    login = api.get(LOGIN, follow_redirects=False)
    approved = github.authorize(login.headers["location"])
    state = parse_qs(approved[1:])["state"][0]
    response = api.get(
        CALLBACK + (callback.format(state=state) or approved), follow_redirects=False
    )
    assert (response.status_code, response.headers["location"]) == (
        302,
        f"/login?error={reason}",
    )
    assert COOKIE not in api.cookies
    assert oauth.COOKIE not in api.cookies  # the login is over: a retry starts another
    assert accounts(database_url) == []


def test_a_callback_is_spent_once_and_needs_the_browser_that_started_it(
    api: TestClient, github: FakeGitHub, database_url: str
) -> None:
    login = api.get(LOGIN, follow_redirects=False)
    approved = github.authorize(login.headers["location"])
    pending = api.cookies[oauth.COOKIE]
    # Login CSRF: another browser follows the callback of the attacker's login.
    with client(database_url, github) as other:
        response = other.get(CALLBACK + approved, follow_redirects=False)
        assert response.headers["location"] == "/login?error=invalid_state"
        # A cookie of the same browser that the login did not write fails too.
        other.cookies.set(oauth.COOKIE, "not-base64!", path=CALLBACK)
        response = other.get(CALLBACK + approved, follow_redirects=False)
        assert response.headers["location"] == "/login?error=invalid_state"
    assert api.get(CALLBACK + approved, follow_redirects=False).headers["location"] == "/"
    # A replay with a copy of the cookie: the state matches, but GitHub spends a code once.
    api.cookies.set(oauth.COOKIE, pending, path=CALLBACK)
    replay = api.get(CALLBACK + approved, follow_redirects=False)
    assert replay.headers["location"] == "/login?error=provider_error"
    # The pending login of another provider is not a login of GitHub.
    forged = json.loads(base64.urlsafe_b64decode(pending)) | {"provider": "vk"}
    api.cookies.set(
        oauth.COOKIE, base64.urlsafe_b64encode(json.dumps(forged).encode()).decode(), path=CALLBACK
    )
    replay = api.get(CALLBACK + approved, follow_redirects=False)
    assert replay.headers["location"] == "/login?error=invalid_state"


def test_github_login_is_configured_by_its_keys_and_its_flag(
    database_url: str, github: FakeGitHub
) -> None:
    def providers(api: TestClient) -> list[str]:
        return [p["key"] for p in api.get("/api/v1/config").json()["auth_providers"]]

    with client(database_url, github) as api:
        assert providers(api) == ["github"]
        assert api.get("/api/v1/config").json()["auth_providers"][0] == {
            "key": "github",
            "title": "GitHub",
            "kind": "oauth",
        }
    for disabled in (
        client(database_url, github, github_client_id="", github_client_secret=""),
        client(database_url, github, flags=overrides(auth_github=False)),
    ):
        with disabled as api:
            assert providers(api) == []
            for path in (LOGIN, CALLBACK + "?code=c&state=s"):
                response = api.get(path, follow_redirects=False)
                assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")
    with pytest.raises(RuntimeError, match="APX_GITHUB_CLIENT_SECRET"):
        create_app(settings(database_url, github_client_secret=None))
    with pytest.raises(RuntimeError, match="APX_PUBLIC_BASE_URL"):
        create_app(settings(database_url, public_base_url=None))
