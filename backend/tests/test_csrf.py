"""CSRF protection (NFR-SEC-05, ADR-0010): the origin of mutating requests, the double-submit token
and its cookie; and that every mutating route declares the check and is rate limited."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from apparatica.auth import api as auth_api
from apparatica.auth.csrf import COOKIE, HEADER, SAFE_METHODS
from apparatica.auth.throttle import draft_throttle, throttle
from apparatica.captcha import api as captcha_api
from apparatica.core import api as core_api
from apparatica.core.flags import no_overrides
from apparatica.core.settings import Settings
from apparatica.main import create_app
from apparatica.problems import api as problems_api
from apparatica.submissions import api as submissions_api
from apparatica.users import api as users_api
from conftest import CONFIG_DIR, CSRF_TOKEN

# A mutating route that works without a database: logout without a session.
LOGOUT = "/api/v1/auth/logout"
MODULES = (core_api, problems_api, submissions_api, captcha_api, auth_api, users_api)
# The autosave of drafts has its own window: it must not spend the requests of checks.
OWN_WINDOW = {"save_draft": draft_throttle}


def make_client(**settings: object) -> TestClient:
    configured = Settings(
        environment="test",
        database_url="sqlite+aiosqlite:///:memory:",
        config_dir=CONFIG_DIR,
        **settings,  # type: ignore[arg-type]
    )
    return TestClient(create_app(configured, flag_overrides=no_overrides))


@pytest.fixture
def browser() -> Iterator[TestClient]:
    """A client without the token: plain HTTP, so it keeps the cookies it gets."""
    with make_client(cookie_secure=False) as client:
        yield client


def csrf_cookie(response: object) -> str | None:
    headers = [
        value
        for value in response.headers.get_list("set-cookie")  # type: ignore[attr-defined]
        if value.startswith(f"{COOKIE}=")
    ]
    assert len(headers) <= 1
    return headers[0] if headers else None


def test_a_refused_request_gets_the_token_and_passes_with_it(browser: TestClient) -> None:
    refused = browser.post(LOGOUT)
    assert refused.status_code == 403
    assert refused.headers["content-type"] == "application/problem+json"
    body = refused.json()
    assert body["code"] == "CSRF_FAILED"
    assert body["request_id"] == refused.headers["x-request-id"]
    cookie = csrf_cookie(refused)
    assert cookie is not None
    attributes = {part.strip().split("=")[0].lower() for part in cookie.split(";")}
    assert {"max-age", "path", "samesite"} <= attributes
    assert "httponly" not in attributes  # the frontend reads it
    assert "secure" not in attributes  # cookie_secure=False
    assert "samesite=lax" in cookie.lower()

    token = browser.cookies[COOKIE]
    passed = browser.post(LOGOUT, headers={HEADER: token})
    assert passed.status_code == 204
    assert csrf_cookie(passed) is None  # the token stays


def test_reads_set_the_token_once(browser: TestClient) -> None:
    first = browser.get("/api/v1/health")
    assert csrf_cookie(first) is not None
    assert csrf_cookie(browser.get("/api/v1/health")) is None
    browser.cookies.clear()
    browser.cookies.set(COOKIE, "not-a-token")  # broken: replaced
    assert csrf_cookie(browser.get("/api/v1/health")) is not None


def test_the_token_cookie_is_secure_by_default() -> None:
    with make_client() as client:
        cookie = csrf_cookie(client.get("/api/v1/health"))
    assert cookie is not None
    assert "secure" in cookie.lower()


@pytest.mark.parametrize(
    "headers",
    [
        {},  # no header
        {HEADER: "x" * 43},  # another token
        {HEADER: (CSRF_TOKEN[:-1] + "й").encode()},  # not ASCII
        {HEADER: CSRF_TOKEN, "Origin": "https://evil.example"},
        {HEADER: CSRF_TOKEN, "Origin": "null"},
        {HEADER: CSRF_TOKEN, "Origin": "https://testserver"},  # another scheme
        {HEADER: CSRF_TOKEN, "Referer": "https://evil.example/page"},
    ],
)
def test_refused_requests(browser: TestClient, headers: dict[str, Any]) -> None:
    browser.cookies.set(COOKIE, CSRF_TOKEN)
    response = browser.post(LOGOUT, headers=headers)
    assert (response.status_code, response.json()["code"]) == (403, "CSRF_FAILED")
    assert csrf_cookie(response) is None  # the cookie was valid


@pytest.mark.parametrize(
    "headers",
    [
        {},  # not from a browser page: the token decides
        {"Origin": "http://testserver"},
        {"Origin": "HTTP://TestServer"},
        {"Referer": "http://testserver/problems/mux4"},
    ],
)
def test_requests_of_the_site_pass(browser: TestClient, headers: dict[str, str]) -> None:
    browser.cookies.set(COOKIE, CSRF_TOKEN)
    response = browser.post(LOGOUT, headers={HEADER: CSRF_TOKEN} | headers)
    assert response.status_code == 204


def test_the_origin_behind_the_proxy(browser: TestClient) -> None:
    """The origin is the one the request reached: the proxy keeps the host, and `apparatica serve`
    takes the scheme from its X-Forwarded-Proto."""
    browser.cookies.set(COOKIE, CSRF_TOKEN)
    headers = {HEADER: CSRF_TOKEN, "Host": "apparatica.app", "Origin": "https://apparatica.app"}
    assert browser.post("https://apparatica.app" + LOGOUT, headers=headers).status_code == 204
    headers["Origin"] = "https://evil.example"
    assert browser.post("https://apparatica.app" + LOGOUT, headers=headers).status_code == 403


def test_safe_methods_are_not_checked(browser: TestClient) -> None:
    headers = {"Origin": "https://evil.example"}
    assert browser.get("/api/v1/health", headers=headers).status_code == 200
    assert browser.head("/api/v1/health", headers=headers).status_code in (200, 405)


def test_every_mutating_route_is_protected(client: TestClient) -> None:
    """CSRF_FAILED is declared by every mutating operation, and each is rate limited."""
    schema = client.get("/api/v1/openapi.json").json()
    declared = {
        operation["operationId"]: operation
        for item in schema["paths"].values()
        for method, operation in item.items()
        if method.upper() not in SAFE_METHODS
    }
    routes = {
        route.name: route
        for module in MODULES
        for route in module.router.routes
        if isinstance(route, APIRoute) and set(route.methods or ()) - SAFE_METHODS
    }
    assert routes.keys() == declared.keys()  # MODULES are all of them
    assert {"create_submission", "logout", "update_me"} <= routes.keys()
    for name, route in routes.items():
        assert "403" in declared[name]["responses"], name
        calls = {dependency.call for dependency in route.dependant.dependencies}
        assert OWN_WINDOW.get(name, throttle) in calls, name
