"""Deletion of an account 7 days after the user asks, and the export of own data (FR-USR-05)."""

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from test_ingest import LINT, SIM, WRONG, new_waveform, run
from test_sessions import sign_in
from test_submissions_api import CODE, MUX4, PROFILE, RecordingQueue, submit
from test_user_progress import finish

from apparatica.auth.accounts import DELETE_AFTER
from apparatica.auth.models import Consent, Identity, User, UserSession
from apparatica.core.db import Database
from apparatica.core.ids import uuid7
from apparatica.core.settings import Settings
from apparatica.judging.housekeeping import AccountPurge
from apparatica.main import create_app
from apparatica.problems.models import UserProblemStatus
from apparatica.submissions.models import Artifact, Submission, Waveform
from apparatica.submissions.profiles import add_profile
from apparatica.users.models import Draft
from conftest import CONFIG_DIR, ApiClient, MemoryStorage, Postgres


@pytest.fixture
def database_url(postgres: Postgres, catalogue_template: str) -> str:
    """The published problems and a default profile."""
    url = postgres.create_database(template=catalogue_template)

    async def profile(database: Database) -> None:
        async with database.sessions.begin() as session:
            await add_profile(session, PROFILE, default=True)

    run(url, profile)
    return url


@pytest.fixture
def api(database_url: str) -> Iterator[TestClient]:
    settings = Settings(
        environment="test", database_url=database_url, config_dir=CONFIG_DIR, cookie_secure=False
    )
    app = create_app(settings, job_queue=RecordingQueue())
    with ApiClient(app, raise_server_exceptions=False) as client:
        yield client


def checked(api: TestClient, database_url: str, *results: Any, **fields: Any) -> str:
    response = submit(api, **fields)
    assert response.status_code == 202, response.text
    submission_id = str(response.json()["id"])
    finish(api, database_url, submission_id, *results)
    return submission_id


def set_delete_at(database_url: str, user_id: uuid.UUID, when: datetime | None) -> None:
    async def scenario(database: Database) -> None:
        async with database.sessions.begin() as session:
            await session.execute(update(User).where(User.id == user_id).values(delete_at=when))

    run(database_url, scenario)


class Files(MemoryStorage):
    """Fails to delete the key "broken"."""

    def delete(self, bucket: str, key: str) -> None:
        if key == "broken":
            raise ClientError({"Error": {"Code": "InternalError"}}, "DeleteObject")
        super().delete(bucket, key)


def test_the_routes_need_a_session(api: TestClient) -> None:
    for method, path in (
        ("DELETE", "/api/v1/me"),
        ("POST", "/api/v1/me/restore"),
        ("GET", "/api/v1/me/export"),
    ):
        response = api.request(method, path)
        assert (response.status_code, response.json()["code"]) == (401, "UNAUTHENTICATED")


def test_deletion_is_asked_and_cancelled(api: TestClient, database_url: str) -> None:
    sign_in(api, database_url)
    assert api.get("/api/v1/me").json()["delete_at"] is None
    before = datetime.now(UTC)
    asked = api.delete("/api/v1/me")
    assert asked.status_code == 202, asked.text
    delete_at = datetime.fromisoformat(asked.json()["delete_at"])
    assert before + DELETE_AFTER <= delete_at <= datetime.now(UTC) + DELETE_AFTER
    again = api.delete("/api/v1/me")  # keeps the time
    assert datetime.fromisoformat(again.json()["delete_at"]) == delete_at
    assert api.get("/api/v1/me").json()["delete_at"] == asked.json()["delete_at"]

    hidden = api.get("/api/v1/users/ada")  # at once, while the session stays
    assert (hidden.status_code, hidden.json()["code"]) == (404, "NOT_FOUND")
    assert api.get("/api/v1/me/export").status_code == 200

    restored = api.post("/api/v1/me/restore")
    assert restored.status_code == 200
    assert restored.json()["delete_at"] is None
    assert api.post("/api/v1/me/restore").json()["delete_at"] is None  # nothing to cancel
    assert api.get("/api/v1/users/ada").status_code == 200


def test_sessions_end_at_the_time_of_deletion(api: TestClient, database_url: str) -> None:
    user = sign_in(api, database_url)
    assert api.delete("/api/v1/me").status_code == 202
    assert api.get("/api/v1/me").status_code == 200  # the session is cached with the time
    set_delete_at(database_url, user.id, datetime.now(UTC) - timedelta(seconds=1))
    api.app.state.sessions._cache = None  # type: ignore[attr-defined]  # read the row again
    response = api.get("/api/v1/me")
    assert (response.status_code, response.json()["code"]) == (401, "UNAUTHENTICATED")


def test_the_export_has_the_own_data(api: TestClient, database_url: str) -> None:
    sign_in(api, database_url, nick="grace")
    checked(api, database_url, LINT, SIM)  # of another user
    user = sign_in(api, database_url, email="ada@example.com")
    accepted = checked(api, database_url, LINT, SIM, kind="submit")
    wrong = checked(api, database_url, LINT, WRONG, code=CODE + "\n// v2")
    assert api.put(
        "/api/v1/me/drafts/mux4", json={"code": "draft", "problem_version": MUX4}
    ).is_success

    async def logins(database: Database) -> None:
        async with database.sessions.begin() as session:
            session.add(
                Identity(
                    id=uuid7(),
                    user_id=user.id,
                    provider="email",
                    subject="ada@example.com",
                    email="ada@example.com",
                )
            )
            session.add(Consent(user_id=user.id, document="terms", version=date(2026, 11, 3)))

    run(database_url, logins)
    response = api.get("/api/v1/me/export")
    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"] == 'attachment; filename="apparatica-ada.json"'
    assert response.headers["cache-control"] == "private, no-store"
    body = json.loads(response.text)
    assert body["format"] == "apparatica-export/1"
    assert body["user"]["nick"] == "ada"
    assert body["user"]["email"] == "ada@example.com"
    assert [item["provider"] for item in body["identities"]] == ["email"]
    assert [(item["document"], item["version"]) for item in body["consents"]] == [
        ("terms", "2026-11-03")
    ]
    assert [item["id"] for item in body["submissions"]] == [wrong, accepted]  # newest first
    first = body["submissions"][1]
    assert (first["problem"], first["kind"], first["status"]) == ("mux4", "submit", "accepted")
    assert first["code"] == CODE
    assert int(first["seed"]) >= 0
    assert first["toolchain_profile"] == PROFILE.id
    assert [(item["problem"], item["code"]) for item in body["drafts"]] == [("mux4", "draft")]


def test_the_purge_deletes_accounts_past_their_time(api: TestClient, database_url: str) -> None:
    ada = sign_in(api, database_url)
    solved = checked(api, database_url, LINT, SIM, kind="submit")
    assert api.put(
        "/api/v1/me/drafts/mux4", json={"code": "draft", "problem_version": MUX4}
    ).is_success
    grace = sign_in(api, database_url, nick="grace")
    kept = checked(api, database_url, LINT, SIM, kind="submit")
    now = datetime.now(UTC)
    set_delete_at(database_url, ada.id, now - timedelta(seconds=1))
    set_delete_at(database_url, grace.id, now + timedelta(days=1))  # not yet
    storage = Files()

    async def scenario(database: Database) -> None:
        async with database.sessions.begin() as session:
            for owner, key in ((solved, "ada-log"), (kept, "grace-log")):
                storage.put("artifacts", key, b"x", "text/plain")
                session.add(
                    Artifact(
                        id=uuid7(),
                        submission_id=uuid.UUID(owner),
                        kind="log",
                        storage_key=key,
                        size_bytes=1,
                        sha256="0" * 64,
                    )
                )
            session.add(
                Identity(id=uuid7(), user_id=ada.id, provider="github", subject="1", email=None)
            )
        purge = AccountPurge(database, storage, "artifacts", clock=lambda: now)
        assert await purge() == 1
        assert await purge() == 0
        async with database.sessions() as session:
            assert list(await session.scalars(select(User.nick))) == ["grace"]
            assert {str(id_) for id_ in await session.scalars(select(Submission.id))} == {kept}
            for table in (Identity, UserSession, Draft, UserProblemStatus):
                left = await session.scalar(
                    select(func.count()).select_from(table).where(table.user_id == ada.id)
                )
                assert left == 0, table
        assert list(storage.objects) == [("artifacts", "grace-log")]

    run(database_url, scenario)
    response = api.get("/api/v1/users/ada")
    assert response.status_code == 404


def test_the_purge_waits_for_checks_waveforms_and_files(api: TestClient, database_url: str) -> None:
    ada = sign_in(api, database_url)
    going = submit(api).json()["id"]  # queued
    now = datetime.now(UTC)
    set_delete_at(database_url, ada.id, now)
    storage = Files()

    async def scenario(database: Database) -> None:
        purge = AccountPurge(database, storage, "artifacts", clock=lambda: now)
        assert await purge() == 0  # the check goes on
        async with database.sessions.begin() as session:
            await session.execute(
                update(Submission)
                .where(Submission.id == uuid.UUID(going))
                .values(status="internal_error")
            )
        waveform = await new_waveform(database, uuid.UUID(going))  # pending
        assert await purge() == 0  # the worker may still upload its file
        async with database.sessions.begin() as session:
            await session.execute(
                update(Waveform).where(Waveform.id == waveform).values(status="failed")
            )
            session.add(
                Artifact(
                    id=uuid7(),
                    submission_id=uuid.UUID(going),
                    kind="log",
                    storage_key="broken",
                    size_bytes=1,
                    sha256="0" * 64,
                )
            )
        assert await purge() == 0  # its file is not deleted
        async with database.sessions.begin() as session:
            await session.execute(update(Artifact).values(storage_key="fixed"))
        assert await purge() == 1

    run(database_url, scenario)
