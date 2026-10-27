"""Guests and their limits (FR-GST-01/04, NFR-SEC-06, specs/07 §3): the signed cookie, access by
the author, the list of own submissions, the quotas of checks and the rate limits."""

import asyncio
import shutil
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from test_submissions_api import CODE, PROFILE, RecordingQueue, run

from apparatica.auth.guests import COOKIE, GuestCookies
from apparatica.core.db import Database
from apparatica.core.errors import ApiError
from apparatica.core.ids import uuid7
from apparatica.core.platform import Quota, Window, load_platform_config
from apparatica.core.ratelimit import ClientAddresses, RateLimiter, rate_limited
from apparatica.core.settings import Settings
from apparatica.main import create_app
from apparatica.problems.models import Problem, ProblemVersion
from apparatica.submissions.models import Submission
from apparatica.submissions.profiles import add_profile
from apparatica.submissions.quotas import Quotas
from conftest import CONFIG_DIR, Postgres, as_guest

KEY = b"k" * 32


def request(cookie: str | None = None, host: str | None = "203.0.113.7") -> Request:
    headers = [(b"cookie", f"{COOKIE}={cookie}".encode())] if cookie is not None else []
    client = (host, 50000) if host is not None else None
    return Request({"type": "http", "headers": headers, "client": client})


def test_the_guest_cookie_is_signed() -> None:
    cookies = GuestCookies(KEY, secure=True)
    guest = uuid.uuid4()
    assert cookies.read(request(cookies.value(guest))) == guest
    assert cookies.read(request()) is None
    other_key = GuestCookies(b"o" * 32, secure=True).value(guest)
    forged_id = f"{uuid.uuid4()}.{cookies.value(guest).partition('.')[2]}"
    for broken in (other_key, forged_id, str(guest), "not-a-uuid.mac", ""):
        assert cookies.read(request(broken)) is None
    with pytest.raises(ValueError, match="32 bytes"):
        GuestCookies(b"short", secure=True)


def test_client_addresses_are_salted_hashes() -> None:
    addresses = ClientAddresses(b"s" * 32)

    def of(host: str | None) -> str | None:
        return addresses.hash(request(host=host))

    assert of("203.0.113.7") == of("203.0.113.7") != of("203.0.113.8")
    assert of("::ffff:203.0.113.7") == of("203.0.113.7")
    # One host gets a whole IPv6 /64.
    assert of("2001:db8:1:2::1") == of("2001:db8:1:2:ffff::9") != of("2001:db8:1:3::1")
    assert of("testclient") is not None
    assert of(None) is None
    assert len(of("203.0.113.7") or "") == 64
    assert ClientAddresses(b"t" * 32).hash(request()) != of("203.0.113.7")


@pytest.fixture(params=["memory", "valkey"])
def cache_url(request: pytest.FixtureRequest) -> str | None:
    """No cache (counters in the process), then valkey-cache."""
    return None if request.param == "memory" else str(request.getfixturevalue("valkey_url"))


def test_a_moving_window(cache_url: str | None) -> None:
    async def scenario() -> None:
        limiter = RateLimiter.connect(cache_url)
        window = Window(limit=2, window_s=60)
        key = str(uuid.uuid4())  # the session Valkey is shared by the tests
        assert await limiter.hit(window, key, "a") is None
        assert await limiter.hit(window, key, "a") is None
        retry = await limiter.hit(window, key, "a")
        assert retry is not None
        assert 59 <= retry <= 60
        assert await limiter.hit(window, key, "b") is None  # its own counter
        state = await limiter.state(window, key, "a")
        assert state.remaining == 0
        assert state.reset_at is not None
        assert (await limiter.state(window, key, "c")).remaining == 2

    asyncio.run(scenario())


def test_an_unreachable_cache_lets_requests_through() -> None:
    async def scenario() -> None:
        limiter = RateLimiter.connect("redis://127.0.0.1:1/0")
        window = Window(limit=1, window_s=60)
        for _ in range(3):
            assert await limiter.hit(window, "x", "a") is None
        assert (await limiter.state(window, "x", "a")).remaining == 1

    asyncio.run(scenario())


def test_rate_limited_errors() -> None:
    error = rate_limited("checks", "spent", limit=10, window_s=3600, retry_after_s=760.2)
    assert isinstance(error, ApiError)
    assert error.params == {"quota": "checks", "limit": 10, "window_s": 3600, "retry_after_s": 761}
    assert error.headers == {"Retry-After": "761"}
    bare = rate_limited("concurrent", "busy", limit=1)
    assert (bare.params, bare.headers) == ({"quota": "concurrent", "limit": 1}, None)
    assert rate_limited("x", "now", limit=1, retry_after_s=0.0).params == {
        "quota": "x",
        "limit": 1,
        "retry_after_s": 1,
    }


def test_the_waveform_quota() -> None:
    async def scenario() -> None:
        config = load_platform_config(CONFIG_DIR)
        quota = Quota(checks_per_hour=10, concurrent=1, heavy_per_day=0, waveforms_per_hour=2)
        quotas = Quotas(quota, RateLimiter.connect(None), config.rate_limits)
        guest = uuid.uuid4()
        await quotas.admit_waveform(guest)
        await quotas.admit_waveform(guest)
        with pytest.raises(ApiError) as spent:
            await quotas.admit_waveform(guest)
        assert spent.value.params is not None
        assert spent.value.params["quota"] == "waveforms"
        assert 3500 < spent.value.params["retry_after_s"] <= 3600
        none = Quota(checks_per_hour=10, concurrent=1, heavy_per_day=0, waveforms_per_hour=0)
        with pytest.raises(ApiError):
            await Quotas(none, RateLimiter.connect(None), config.rate_limits).admit_waveform(guest)

    asyncio.run(scenario())


# The API on Postgres.


@pytest.fixture
def database_url(postgres: Postgres, catalogue_template: str) -> str:
    url = postgres.create_database(template=catalogue_template)

    async def profile(database: Database) -> None:
        async with database.sessions.begin() as session:
            await add_profile(session, PROFILE, default=True)

    run(url, profile)
    return url


@pytest.fixture
def queue() -> RecordingQueue:
    return RecordingQueue()


def app_client(
    database_url: str, queue: RecordingQueue, config_dir: Path = CONFIG_DIR, **settings: Any
) -> TestClient:
    configured = Settings(
        environment="test", database_url=database_url, config_dir=config_dir, **settings
    )
    return TestClient(create_app(configured, job_queue=queue), raise_server_exceptions=False)


@pytest.fixture
def api(database_url: str, queue: RecordingQueue) -> Iterator[TestClient]:
    with app_client(database_url, queue, cookie_secure=False) as client:
        yield client


def submit(api: TestClient, **fields: Any) -> Any:
    body = {"problem": "mux4", "version": 1, "kind": "run", "code": CODE} | fields
    return api.post("/api/v1/submissions", json=body)


def store(
    url: str,
    guest: uuid.UUID,
    *,
    problem: str = "mux4",
    kind: str = "run",
    status: str = "accepted",
    age: timedelta = timedelta(0),
) -> uuid.UUID:
    """A submission of `guest` created `age` ago."""

    async def scenario(database: Database) -> uuid.UUID:
        async with database.sessions.begin() as session:
            version = await session.scalar(
                select(ProblemVersion)
                .join(Problem, Problem.current_version_id == ProblemVersion.id)
                .where(Problem.slug == problem)
            )
            assert version is not None
            submission = Submission(
                id=uuid7(),
                problem_version_id=version.id,
                kind=kind,
                code=CODE,
                seed=1,
                toolchain_profile_id=PROFILE.id,
                queue_class="light",
                guest_id=guest,
                status=status,
                created_at=datetime.now(UTC) - age,
            )
            session.add(submission)
        return submission.id

    result: uuid.UUID = run(url, scenario)
    return result


def test_the_first_submission_sets_the_guest_cookie(
    database_url: str, queue: RecordingQueue
) -> None:
    with app_client(database_url, queue) as client:
        created = submit(client)
        assert created.status_code == 202, created.text
        cookie = created.headers["set-cookie"]
        value = cookie.split(";")[0].removeprefix(f"{COOKIE}=")
        attributes = {part.strip().lower() for part in cookie.split(";")[1:]}
        assert attributes == {
            "httponly",
            "max-age=31536000",
            "path=/",
            "samesite=lax",
            "secure",
        }
        guest = uuid.UUID(value.partition(".")[0])

        # With the cookie, the next submission keeps the guest and sets nothing.
        client.cookies.set(COOKIE, value)
        again = submit(client)  # a Run of the same problem: it preempts the first one
        assert again.status_code == 202, again.text
        assert "set-cookie" not in again.headers

    async def stored(database: Database) -> list[tuple[uuid.UUID | None, str | None]]:
        async with database.sessions() as session:
            rows = await session.execute(select(Submission.guest_id, Submission.client_ip_hash))
            return [(guest_id, address) for guest_id, address in rows]

    [(first_guest, address), (second_guest, same_address)] = run(database_url, stored)
    assert first_guest == second_guest == guest
    assert address is not None
    assert len(address) == 64
    assert address == same_address


def test_submissions_belong_to_their_author(api: TestClient) -> None:
    submission = submit(api).json()["id"]
    path = f"/api/v1/submissions/{submission}"
    assert api.get(path).status_code == 200
    author = api.cookies[COOKIE]
    other = api.app.state.guest_cookies.value(uuid.uuid4())  # type: ignore[attr-defined]
    for cookie in (None, other, author + "x"):
        api.cookies.clear()
        if cookie is not None:
            api.cookies.set(COOKIE, cookie)
        for response in (api.get(path), api.post(f"{path}/cancel")):
            assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")
        assert api.get("/api/v1/submissions").json()["items"] == []


def test_the_list_of_own_submissions(api: TestClient, database_url: str) -> None:
    guest = uuid.uuid4()
    ids = [
        store(database_url, guest, problem=problem, age=timedelta(minutes=minutes))
        for problem, minutes in [
            ("mux4", 50),
            ("sync-fifo", 40),
            ("mux4", 30),
            ("mux4", 20),
            ("sync-fifo", 10),
        ]
    ]
    store(database_url, uuid.uuid4())  # someone else
    as_guest(api, guest)

    pages, cursor = [], None
    while True:
        query = {"limit": 2} | ({"cursor": cursor} if cursor is not None else {})
        response = api.get("/api/v1/submissions", params=query)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "private, no-store"
        body = response.json()
        pages.append([item["id"] for item in body["items"]])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    newest_first = [str(i) for i in reversed(ids)]
    assert pages == [newest_first[:2], newest_first[2:4], newest_first[4:]]
    assert body["quota"]["checks"] == {"limit": 10, "remaining": 5, "reset_at": None}

    mux4 = api.get("/api/v1/submissions", params={"problem": "mux4"}).json()
    assert [item["id"] for item in mux4["items"]] == [str(ids[i]) for i in (3, 2, 0)]
    first = mux4["items"][0]
    assert (first["problem"], first["problem_title"], first["kind"], first["status"]) == (
        "mux4",
        "Мультиплексор 4:1",
        "run",
        "accepted",
    )

    for bad in ("garbage", "eA", "MjAyNnww"):  # not base64 / no separator / no id
        response = api.get("/api/v1/submissions", params={"cursor": bad})
        assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")

    api.cookies.clear()
    new = api.get("/api/v1/submissions").json()
    assert new["items"] == []
    assert new["next_cursor"] is None
    assert new["quota"] == {
        "checks": {"limit": 10, "remaining": 10, "reset_at": None},
        "waveforms": {"limit": 5, "remaining": 5, "reset_at": None},
    }


def test_the_hourly_quota_of_checks(api: TestClient, database_url: str) -> None:
    guest = uuid.uuid4()
    oldest = datetime.now(UTC) - timedelta(minutes=50)
    store(database_url, guest, age=timedelta(minutes=50))
    for minutes in range(41, 49):
        store(database_url, guest, age=timedelta(minutes=minutes))
    store(database_url, guest, status="internal_error", age=timedelta(minutes=5))  # not counted
    store(database_url, guest, age=timedelta(minutes=61))  # out of the window
    as_guest(api, guest)

    last = submit(api)
    assert last.status_code == 202, last.text
    checks = last.json()["quota"]["checks"]
    assert (checks["limit"], checks["remaining"]) == (10, 0)
    reset_at = datetime.fromisoformat(checks["reset_at"])
    assert abs(reset_at - (oldest + timedelta(hours=1))) < timedelta(seconds=30)

    spent = submit(api)
    assert spent.status_code == 429
    body = spent.json()
    assert body["code"] == "RATE_LIMITED"
    params = body["params"]
    assert {key: params[key] for key in ("quota", "limit", "window_s")} == {
        "quota": "checks",
        "limit": 10,
        "window_s": 3600,
    }
    assert 9 * 60 < params["retry_after_s"] < 11 * 60
    assert spent.headers["retry-after"] == str(params["retry_after_s"])
    assert body["detail"] == "Guest limit is 10 checks per hour"


def test_concurrent_checks(api: TestClient, database_url: str, queue: RecordingQueue) -> None:
    guest = uuid.uuid4()
    as_guest(api, guest)
    pending_run = store(database_url, guest, status="running")
    # A new Run of the same problem preempts the unfinished one: it does not count.
    assert submit(api).status_code == 202
    assert queue.cancels == [(pending_run, "preempted")]
    # Another problem waits for the checks of the guest.
    busy = submit(api, problem="sync-fifo")
    assert busy.status_code == 429
    assert busy.json()["params"] == {"quota": "concurrent", "limit": 1}
    assert "retry-after" not in busy.headers

    async def finish_all(database: Database) -> None:
        async with database.sessions.begin() as session:
            await session.execute(update(Submission).values(status="accepted"))

    run(database_url, finish_all)
    # A Submit is never preempted, so a Run of the same problem waits for it too.
    assert submit(api, kind="submit").status_code == 202
    assert submit(api).json()["params"]["quota"] == "concurrent"


def test_heavy_problems_are_not_for_guests(api: TestClient, database_url: str) -> None:
    async def heavy(database: Database) -> None:
        async with database.sessions.begin() as session:
            await session.execute(update(ProblemVersion).values(resource_class="heavy"))

    run(database_url, heavy)
    response = submit(api)
    assert (response.status_code, response.json()["code"]) == (403, "HEAVY_NOT_ALLOWED")


def test_rate_limits_of_requests(database_url: str, queue: RecordingQueue, tmp_path: Path) -> None:
    for name in ("difficulties.yaml", "catalog.yaml", "limits.yaml"):
        shutil.copy(CONFIG_DIR / name, tmp_path / name)
    (tmp_path / "rate-limits.yaml").write_text(
        "requests_per_ip: {limit: 3, window_s: 60}\n"
        "requests_per_author: {limit: 2, window_s: 60}\n"
        "checks_per_ip: {limit: 1, window_s: 3600}\n"
        "captcha:\n"
        "  per_guest: {limit: 3, window_s: 60}\n"
        "  per_ip: {limit: 10, window_s: 60}\n"
        "  max_number: 1000\n"
        "  expires_s: 600\n",
        encoding="utf-8",
    )
    with app_client(database_url, queue, tmp_path, cookie_secure=False) as client:
        as_guest(client)
        cancel = f"/api/v1/submissions/{uuid.uuid4()}/cancel"
        assert [client.post(cancel).status_code for _ in range(2)] == [404, 404]
        by_guest = client.post(cancel)
        assert by_guest.status_code == 429
        params = by_guest.json()["params"]
        assert (params["quota"], params["limit"], params["window_s"]) == ("requests", 2, 60)
        assert 0 < int(by_guest.headers["retry-after"]) <= 60
        client.cookies.clear()
        by_address = client.post(cancel)  # the fourth request of the address
        assert (by_address.status_code, by_address.json()["params"]["limit"]) == (429, 3)
        # Reads are not limited.
        assert client.get("/api/v1/submissions").status_code == 200

    with app_client(database_url, queue, tmp_path, cookie_secure=False) as client:
        assert submit(client).status_code == 202
        client.cookies.clear()  # a guest who drops the cookie
        dropped = submit(client)
        assert dropped.status_code == 429
        assert dropped.json()["params"]["quota"] == "checks_per_ip"
        assert 3500 < dropped.json()["params"]["retry_after_s"] <= 3600
