"""Periodic tasks of the leading ingestor: the leader lock, the watchdog, retention of artifacts,
guest submissions and address hashes (ADR-0009, specs/07 §3, §4.4, ОВ-13, NFR-PRIV-01)."""

import asyncio
import json
import uuid
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import boto3
import pytest
import redis.asyncio
from botocore.exceptions import ClientError
from moto import mock_aws
from sqlalchemy import func, select, update
from test_ingest import NOW, new_submission, run

from apparatica.core.db import Database
from apparatica.core.ids import uuid7
from apparatica.core.settings import Settings
from apparatica.core.storage import Storage
from apparatica.judging.housekeeping import (
    WATCHDOG_TIMEOUT,
    AddressPurge,
    ArtifactPurge,
    GuestPurge,
    Housekeeping,
    Periodic,
    Watchdog,
)
from apparatica.judging.leader import LEADER_KEY, Leadership
from apparatica.submissions.models import Artifact, StageResult, Submission
from conftest import CONFIG_DIR, Postgres
from judge.core.jobs import ATTEMPT_MAX, lease_key, submission_stream_key
from judge.core.limits import CHECK_OVERHEAD_S, load_resource_classes
from judge.core.verdict import VerdictDetail

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

CLASSES = load_resource_classes(CONFIG_DIR / "resource-classes.yaml")
GRACE_S = 60
# mux4 runs precheck, lint and sim_run in the light class: 10 + 10 + 30 s.
MUX4_RUN_S = 10 + 10 + 30 + CHECK_OVERHEAD_S
DEADLINE = timedelta(seconds=ATTEMPT_MAX * MUX4_RUN_S + GRACE_S)


@pytest.fixture
def database_url(postgres: Postgres, catalogue_template: str) -> str:
    return postgres.create_database(template=catalogue_template)


@pytest.fixture
def valkey(valkey_url: str) -> str:
    """valkey-queue for one test: empty before it."""
    redis.Redis.from_url(valkey_url).flushdb()
    return valkey_url


async def set_state(database: Database, submission_id: uuid.UUID, **values: Any) -> None:
    async with database.sessions.begin() as session:
        await session.execute(
            update(Submission).where(Submission.id == submission_id).values(**values)
        )


async def status(database: Database, submission_id: uuid.UUID) -> tuple[str, Any]:
    async with database.sessions() as session:
        submission = await session.get(Submission, submission_id)
        assert submission is not None
        return submission.status, submission.verdict_detail


def test_one_ingestor_leads(valkey: str) -> None:
    async def scenario() -> None:
        client = redis.asyncio.Redis.from_url(valkey)
        a, b = Leadership(client, "a", ttl_s=0.3), Leadership(client, "b", ttl_s=0.3)
        assert await a.hold()
        assert not await b.hold()
        assert await a.hold()  # renewed
        await asyncio.sleep(0.5)  # a stopped renewing: its lock expired
        assert await b.hold()
        assert not await a.hold()
        await a.release()  # not a's lock any more
        assert await client.get(LEADER_KEY) == b"b"
        await b.release()
        assert await a.hold()
        await client.aclose()

    asyncio.run(scenario())


def test_the_watchdog_ends_stuck_checks_only(database_url: str, valkey: str) -> None:
    async def scenario(database: Database) -> None:
        client = redis.asyncio.Redis.from_url(valkey)
        stuck, held, recent, queued = [await new_submission(database) for _ in range(4)]
        late = NOW - DEADLINE - timedelta(seconds=1)
        for submission in (stuck, held):
            await set_state(database, submission, status="running", started_at=late)
        await set_state(
            database, recent, status="running", started_at=NOW - DEADLINE + timedelta(seconds=1)
        )
        await set_state(database, queued, created_at=late)
        await client.set(lease_key(held), "worker-a")  # a worker still runs it

        watchdog = Watchdog(database, client, CLASSES, GRACE_S, clock=lambda: NOW)
        assert await watchdog() == 1
        assert await status(database, stuck) == (
            "internal_error",
            VerdictDetail(error_codes=[WATCHDOG_TIMEOUT]).model_dump(mode="json"),
        )
        for other, expected in ((held, "running"), (recent, "running"), (queued, "queued")):
            assert (await status(database, other))[0] == expected
        entries = cast(
            list[tuple[bytes, dict[bytes, bytes]]],
            await client.xrange(submission_stream_key(stuck)),
        )
        assert [json.loads(fields[b"e"])["status"] for _, fields in entries] == ["internal_error"]
        assert await watchdog() == 0  # nothing left
        await client.aclose()

    run(database_url, scenario)


def test_expired_files_are_deleted_and_their_rows_kept(database_url: str, tmp_path: Path) -> None:
    async def scenario(database: Database) -> None:
        submission = await new_submission(database)
        names = {
            "expired": NOW - timedelta(seconds=1),
            "purged": NOW - timedelta(days=1),
            "fresh": NOW + timedelta(days=1),
            "kept": None,
        }
        async with database.sessions.begin() as session:
            for name, expires_at in names.items():
                session.add(
                    Artifact(
                        id=uuid7(),
                        submission_id=submission,
                        kind="fst",
                        storage_key=name,
                        size_bytes=1,
                        sha256="0" * 64,
                        expires_at=expires_at,
                        purged_at=NOW - timedelta(hours=1) if name == "purged" else None,
                    )
                )
        with mock_aws():
            settings = Settings(environment="test", s3_region="us-east-1")
            s3: S3Client = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket="artifacts")
            for name in names:
                s3.put_object(Bucket="artifacts", Key=name, Body=b"x")
            purge = ArtifactPurge(database, Storage(settings), "artifacts", clock=lambda: NOW)
            assert await purge() == 1
            assert await purge() == 0
            left = [o["Key"] for o in s3.list_objects_v2(Bucket="artifacts").get("Contents", [])]
        assert sorted(left) == ["fresh", "kept", "purged"]  # "purged" was deleted by hand, say
        async with database.sessions() as session:
            rows = await session.execute(
                select(Artifact.storage_key, Artifact.purged_at).order_by(Artifact.storage_key)
            )
            assert {key: purged for key, purged in rows} == {
                "expired": NOW,
                "fresh": None,
                "kept": None,
                "purged": NOW - timedelta(hours=1),
            }

    run(database_url, scenario)


class FlakyStorage(Storage):
    """Fails to delete the key "broken"."""

    def delete(self, bucket: str, key: str) -> None:
        if key == "broken":
            raise ClientError({"Error": {"Code": "InternalError"}}, "DeleteObject")
        super().delete(bucket, key)


def test_old_guest_submissions_are_deleted_with_their_files(database_url: str) -> None:
    async def scenario(database: Database) -> None:
        old = NOW - timedelta(days=14, seconds=1)
        submissions: dict[str, uuid.UUID] = {}
        for name, created_at, state in [
            ("old", old, "accepted"),
            ("old-broken", old, "wrong_answer"),
            ("old-running", old, "running"),  # the ingestor finishes it first
            ("recent", NOW - timedelta(days=13), "accepted"),
            ("no-guest", old, "accepted"),  # not a guest submission
        ]:
            submission = await new_submission(database)
            values: dict[str, Any] = {"created_at": created_at, "status": state}
            if name == "no-guest":
                values["guest_id"] = None
            await set_state(database, submission, **values)
            submissions[name] = submission
        files = {"log": "old", "fst": "old-purged", "events": "broken"}
        async with database.sessions.begin() as session:
            session.add(
                StageResult(
                    submission_id=submissions["old"],
                    stage_key="lint",
                    stage_type="lint",
                    ordinal=1,
                    status="passed",
                )
            )
            for kind, key in files.items():
                owner = "old-broken" if key == "broken" else "old"
                session.add(
                    Artifact(
                        id=uuid7(),
                        submission_id=submissions[owner],
                        kind=kind,
                        storage_key=key,
                        size_bytes=1,
                        sha256="0" * 64,
                        purged_at=NOW if key == "old-purged" else None,
                    )
                )
        with mock_aws():
            settings = Settings(environment="test", s3_region="us-east-1")
            s3: S3Client = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket="artifacts")
            for key in ("old", "broken", "other"):
                s3.put_object(Bucket="artifacts", Key=key, Body=b"x")
            purge = GuestPurge(
                database, FlakyStorage(settings), "artifacts", days=14, clock=lambda: NOW
            )
            assert await purge() == 1
            assert await purge() == 0  # "old-broken" waits for its file
            left = [o["Key"] for o in s3.list_objects_v2(Bucket="artifacts").get("Contents", [])]
        assert sorted(left) == ["broken", "other"]
        async with database.sessions() as session:
            ids = set(await session.scalars(select(Submission.id)))
            assert ids == {submissions[name] for name in submissions if name != "old"}
            assert await session.scalar(select(func.count()).select_from(StageResult)) == 0
            keys = list(await session.scalars(select(Artifact.storage_key)))
            assert keys == ["broken"]

    run(database_url, scenario)


def test_old_address_hashes_are_cleared(database_url: str) -> None:
    async def scenario(database: Database) -> None:
        ages = {"old": timedelta(days=30, seconds=1), "recent": timedelta(days=29)}
        for name, age in ages.items():
            submission = await new_submission(database)
            await set_state(database, submission, created_at=NOW - age, client_ip_hash=name)
        purge = AddressPurge(database, days=30, clock=lambda: NOW)
        assert await purge() == 1
        assert await purge() == 0
        async with database.sessions() as session:
            hashes = list(await session.scalars(select(Submission.client_ip_hash)))
            assert sorted(hashes, key=lambda value: value or "") == [None, "recent"]

    run(database_url, scenario)


def test_only_the_leader_runs_the_tasks_and_a_failure_stays_inside(valkey: str) -> None:
    async def scenario() -> None:
        client = redis.asyncio.Redis.from_url(valkey)
        runs: list[str] = []

        async def ok() -> int:
            runs.append("ok")
            return 0

        async def broken() -> int:
            runs.append("broken")
            raise RuntimeError("a bug")

        tasks = [Periodic("broken", 3600, broken), Periodic("ok", 3600, ok)]
        leader = Housekeeping(Leadership(client, "a"), tasks)
        follower = Housekeeping(Leadership(client, "b"), [Periodic("ok", 0, ok)])
        assert await leader.tick()
        assert not await follower.tick()
        assert await leader.tick()  # not due again
        assert runs == ["broken", "ok"]
        stop = asyncio.Event()
        stop.set()
        await leader.run(stop)  # stopping gives up the lock
        assert await client.get(LEADER_KEY) is None
        await client.aclose()

    asyncio.run(scenario())
