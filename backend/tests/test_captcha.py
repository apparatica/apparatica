"""The captcha before guest checks (FR-GST-05, ADR-0010): ALTCHA challenges, when a captcha is
needed, and the API."""

import asyncio
import base64
import hashlib
import json
import uuid
from collections.abc import Iterator, Mapping
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_guests import submit
from test_submissions_api import PROFILE, RecordingQueue, run

from apparatica.captcha.altcha import Altcha
from apparatica.captcha.service import Captcha
from apparatica.core.db import Database
from apparatica.core.errors import ApiError
from apparatica.core.flags import FeatureFlags, Overrides
from apparatica.core.platform import CaptchaRules, Window
from apparatica.core.ratelimit import RateLimiter
from apparatica.core.settings import Settings
from apparatica.main import create_app
from apparatica.submissions.profiles import add_profile
from conftest import CONFIG_DIR, Postgres

KEY = b"c" * 32
NOW = 1_800_000_000.0


def solve(challenge: Mapping[str, Any], **changes: Any) -> str:
    """What the widget sends: the number found by brute force, as base64 JSON."""
    salt = challenge["salt"]
    number = next(
        n
        for n in range(challenge["maxnumber"] + 1)
        if hashlib.sha256(f"{salt}{n}".encode()).hexdigest() == challenge["challenge"]
    )
    fields = ("algorithm", "challenge", "salt", "signature")
    payload = {key: challenge[key] for key in fields} | {"number": number} | changes
    return base64.b64encode(json.dumps(payload).encode()).decode()


def altcha(clock: float = NOW) -> Altcha:
    return Altcha(KEY, max_number=1000, expires_s=600, clock=lambda: clock)


def test_a_challenge_is_solved_and_verified() -> None:
    issued = altcha().challenge()
    assert issued.algorithm == "SHA-256"
    assert issued.maxnumber == 1000
    assert issued.salt.endswith(f"?expires={int(NOW) + 600}")
    challenge = issued.model_dump()
    assert altcha().verify(solve(challenge)) == issued.signature
    # Another challenge is another one.
    assert altcha().challenge().salt != issued.salt


def test_bad_solutions() -> None:
    challenge = altcha().challenge().model_dump()
    good = json.loads(base64.b64decode(solve(challenge)))
    other_salt = altcha().challenge().salt
    bad = [
        solve(challenge, number=(good["number"] + 1) % 1001),
        solve(challenge, number=True),
        solve(challenge, number=1001),
        solve(challenge, number="1"),
        solve(challenge, algorithm="SHA-512"),
        solve(challenge, signature="0" * 64),
        solve(challenge, salt=other_salt),  # the number does not give the challenge
        base64.b64encode(b"[1, 2]").decode(),
        base64.b64encode(b"\xff").decode(),
        "not base64!",
        "",
    ]
    for payload in bad:
        assert altcha().verify(payload) is None, payload
    # Expired, and signed by another key.
    assert altcha(NOW + 601).verify(solve(challenge)) is None
    stranger = Altcha(b"x" * 32, max_number=1000, expires_s=600, clock=lambda: NOW)
    assert stranger.verify(solve(challenge)) is None
    with pytest.raises(ValueError, match="32 bytes"):
        Altcha(b"short", max_number=1000, expires_s=600)


def flags(captcha: bool) -> FeatureFlags:
    async def overrides() -> Mapping[str, bool]:
        return {"captcha": captcha}

    return FeatureFlags(overrides)


def gate(always: bool = False) -> Captcha:
    rules = CaptchaRules(
        per_guest=Window(limit=2, window_s=60),
        per_ip=Window(limit=3, window_s=60),
        max_number=1000,
        expires_s=600,
    )
    return Captcha(altcha(), RateLimiter.connect(None), rules, flags(always))


def reason(error: pytest.ExceptionInfo[ApiError]) -> str:
    assert error.value.params is not None
    assert error.value.params["challenge_url"] == "/api/v1/captcha/challenge"
    return str(error.value.params["reason"])


def test_a_captcha_after_frequent_checks() -> None:
    async def scenario() -> None:
        captcha = gate()
        guest, other = uuid.uuid4(), uuid.uuid4()
        for _ in range(2):
            await captcha.check(guest, "address", "a needless solution is not looked at")
            await captcha.count(guest, "address")
        with pytest.raises(ApiError) as needed:
            await captcha.check(guest, "address", None)
        assert reason(needed) == "frequent"
        assert needed.value.params is not None
        assert 1 <= needed.value.params["retry_after_s"] <= 60  # the window of the guest
        solution = solve(captcha.altcha.challenge().model_dump())
        await captcha.check(guest, "address", solution)
        with pytest.raises(ApiError) as replayed:
            await captcha.check(guest, "address", solution)
        assert reason(replayed) == "invalid"
        assert replayed.value.params is not None
        assert "retry_after_s" in replayed.value.params  # still frequent: the wait is known
        with pytest.raises(ApiError) as wrong:
            await captcha.check(guest, "address", "garbage")
        assert reason(wrong) == "invalid"

        # The address: a third check from it, by a new guest.
        await captcha.check(other, "address", None)
        await captcha.count(other, "address")
        with pytest.raises(ApiError) as by_address:
            await captcha.check(uuid.uuid4(), "address", None)
        assert reason(by_address) == "frequent"
        await captcha.check(uuid.uuid4(), None, None)  # no address: the guest window only

    asyncio.run(scenario())


def test_the_flag_asks_always() -> None:
    async def scenario() -> None:
        captcha = gate(always=True)
        with pytest.raises(ApiError) as needed:
            await captcha.check(uuid.uuid4(), None, None)
        assert reason(needed) == "always"
        assert needed.value.params is not None
        assert "retry_after_s" not in needed.value.params  # no wait helps
        await captcha.check(uuid.uuid4(), None, solve(captcha.altcha.challenge().model_dump()))

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


def client(database_url: str, queue: RecordingQueue, overrides: Overrides) -> TestClient:
    settings = Settings(
        environment="test", database_url=database_url, config_dir=CONFIG_DIR, cookie_secure=False
    )
    app = create_app(settings, flag_overrides=overrides, job_queue=queue)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def api(database_url: str, queue: RecordingQueue) -> Iterator[TestClient]:
    async def no_flags() -> Mapping[str, bool]:
        return {}

    with client(database_url, queue, no_flags) as test_client:
        yield test_client


def challenge_of(api: TestClient) -> Any:
    response = api.get("/api/v1/captcha/challenge")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    return response.json()


def test_frequent_guest_checks_need_a_captcha(api: TestClient) -> None:
    # Runs of one problem: each preempts the previous one, so the guest is never busy.
    for _ in range(3):
        assert submit(api).status_code == 202
    needed = submit(api)
    assert needed.status_code == 428
    body = needed.json()
    assert body["code"] == "CAPTCHA_REQUIRED"
    params = body["params"]
    assert params.pop("retry_after_s") in range(1, 61)  # config/rate-limits.yaml: 3 per minute
    assert params == {"challenge_url": "/api/v1/captcha/challenge", "reason": "frequent"}

    challenge = challenge_of(api)
    assert challenge["maxnumber"] == 100_000  # config/rate-limits.yaml
    solution = solve(challenge)
    assert submit(api, captcha=solution).status_code == 202
    replayed = submit(api, captcha=solution)
    assert (replayed.status_code, replayed.json()["params"]["reason"]) == (428, "invalid")


def test_the_flag_asks_every_guest_check(database_url: str, queue: RecordingQueue) -> None:
    async def captcha_on() -> Mapping[str, bool]:
        return {"captcha": True}

    with client(database_url, queue, captcha_on) as api:
        needed = submit(api)
        assert (needed.status_code, needed.json()["params"]["reason"]) == (428, "always")
        assert queue.jobs == []
        assert submit(api, captcha=solve(challenge_of(api))).status_code == 202
