"""Artifacts for their author: downloads by presigned URL and recreated FST (specs/07 §4.4,
FR-WAV-05, FR-WAV-06)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from test_submissions_api import CODE, PROFILE, RecordingQueue, run, submit

from apparatica.core.db import Database
from apparatica.core.settings import Settings
from apparatica.judging.ingest import Ingestor
from apparatica.judging.retention import load_retention
from apparatica.main import create_app
from apparatica.submissions.models import Artifact, StageResult, Submission, Waveform
from apparatica.submissions.profiles import add_profile
from apparatica.submissions.tokens import JobTokens
from conftest import CONFIG_DIR, Postgres
from judge.core.jobs import StoredArtifact, TraceKey, WaveformRecord

KEY = "k" * 32
TOKENS = JobTokens(KEY.encode(), ttl_s=3600)
SIGNALS = [
    {"path": "tb_top.clk", "port": "clk", "role": "clock"},
    {"path": "tb_top.sel", "port": "sel", "role": "input"},
    {"path": "tb_top.y", "port": "y", "role": "output"},
    {"path": "tb_top.exp_y", "port": "y", "role": "expected"},
]
METRICS = {
    "tests_total": 4,
    "tests_passed": 1,
    "cycles": 40,
    "seed": 1,
    "first_failure": {"test": "t2", "cycle": 18, "signal": "y"},
    "trace": "recorded",
    "trace_window": [0, 34],
    "trace_cursor_ps": 180_000,
    "trace_signals": SIGNALS,
}
WAVEFORM = {
    "test": "t2",
    "scope": "failure_window",
    "from_cycle": 0,
    "to_cycle": 34,
    "cursor_cycle": 18,
    "cursor_time_ps": 180_000,
    "signals": SIGNALS,
}


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


@pytest.fixture
def api(database_url: str, queue: RecordingQueue) -> Iterator[TestClient]:
    settings = Settings(
        environment="test",
        database_url=database_url,
        config_dir=CONFIG_DIR,
        cookie_secure=False,
        job_token_key=KEY,  # type: ignore[arg-type]  # a SecretStr from a string
        s3_endpoint_url="http://garage:3900",
        s3_public_url="http://s3.localhost:8080",
        s3_access_key_id="GK0000",
        s3_secret_access_key="secret",  # type: ignore[arg-type]
    )
    app = create_app(settings, job_queue=queue)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def failed_run(api: TestClient, database_url: str, *, fst_expires: datetime | None) -> uuid.UUID:
    """A Run that failed an open test with a recorded trace window."""
    submission_id = uuid.UUID(submit(api).json()["id"])
    now = datetime.now(UTC)

    async def finish(database: Database) -> None:
        async with database.sessions.begin() as session:
            await session.execute(
                update(Submission)
                .where(Submission.id == submission_id)
                .values(status="wrong_answer", started_at=now, finished_at=now)
            )
            for ordinal, key in enumerate(("precheck", "lint", "sim_run")):
                sim = key == "sim_run"
                session.add(
                    StageResult(
                        submission_id=submission_id,
                        stage_key=key,
                        stage_type="sim" if sim else key,
                        ordinal=ordinal,
                        status="failed" if sim else "passed",
                        failure_kind="wrong" if sim else None,
                        metrics=METRICS if sim else {},
                        metrics_schema="sim/v1" if sim else None,
                        summary={},
                    )
                )
            for kind, stage, expires_at in (
                ("log", "sim_run", None),
                ("events", None, None),
                ("fst", "sim_run", fst_expires),
            ):
                session.add(
                    Artifact(
                        submission_id=submission_id,
                        stage_key=stage,
                        kind=kind,
                        storage_key=f"2026/10/{submission_id}/1/{kind}",
                        size_bytes=100,
                        sha256="0" * 64,
                        expires_at=expires_at,
                    )
                )

    run(database_url, finish)
    return submission_id


def artifacts(api: TestClient, submission_id: uuid.UUID) -> list[dict[str, Any]]:
    return list(api.get(f"/api/v1/submissions/{submission_id}").json()["artifacts"])


def request(api: TestClient, submission_id: uuid.UUID, **body: Any) -> Any:
    return api.post(f"/api/v1/submissions/{submission_id}/waveform", json=body)


def record(database_url: str, record: WaveformRecord) -> None:
    async def ingest(database: Database) -> None:
        await Ingestor(database, TOKENS, load_retention(CONFIG_DIR)).ingest(record)

    run(database_url, ingest)


def test_an_expired_trace_is_recorded_again(
    api: TestClient, database_url: str, queue: RecordingQueue
) -> None:
    expired = datetime.now(UTC) - timedelta(days=1)
    submission_id = failed_run(api, database_url, fst_expires=expired)
    assert artifacts(api, submission_id) == [
        {"kind": "events", "stage": None, "state": "ready", "size_bytes": 100, "waveform": None},
        {"kind": "log", "stage": "sim_run", "state": "ready", "size_bytes": 100, "waveform": None},
        {
            "kind": "fst",
            "stage": "sim_run",
            "state": "expired",
            "size_bytes": 100,
            "waveform": WAVEFORM,
        },
    ]

    pending = {"kind": "fst", "stage": "sim_run", "state": "pending", "size_bytes": None}
    response = request(api, submission_id)
    assert response.status_code == 202, response.text
    assert response.json() == pending | {"waveform": WAVEFORM}
    assert artifacts(api, submission_id)[-1] == pending | {"waveform": WAVEFORM}
    [(queue_name, job)] = queue.waveforms
    assert queue_name == "judge.light"
    assert (job.stage, job.stages) == ("sim_run", ("precheck", "lint", "sim_run"))
    assert job.first_failure == TraceKey(test="t2", cycle=18, signal="y")
    check = job.check
    assert (check.submission_id, check.kind, check.code) == (submission_id, "run", CODE)
    assert TOKENS.verify(check.token, submission_id).submission_id == submission_id
    # Asked again while it is recorded: the same job, no quota spent.
    assert request(api, submission_id).json()["state"] == "pending"
    assert len(queue.waveforms) == 1
    quota = api.get("/api/v1/submissions").json()["quota"]["waveforms"]
    assert quota["remaining"] == 4

    stored = StoredArtifact(
        kind="fst",
        stage="sim_run",
        key=f"2026/10/{submission_id}/w-{job.waveform_id}/sim_run/trace.fst",
        size_bytes=2500,
        sha256="1" * 64,
    )
    done = WaveformRecord(
        submission_id=submission_id,
        token=check.token,
        waveform_id=job.waveform_id,
        artifact=stored,
    )
    record(database_url, done)
    record(database_url, done)  # redelivered: one artifact
    ready = {"kind": "fst", "stage": "sim_run", "state": "ready", "size_bytes": 2500}
    assert artifacts(api, submission_id)[-1] == ready | {"waveform": WAVEFORM}
    assert request(api, submission_id).json()["state"] == "ready"
    assert len(queue.waveforms) == 1

    response = api.get(
        f"/api/v1/submissions/{submission_id}/artifacts/fst?stage=sim_run", follow_redirects=False
    )
    assert response.status_code == 302
    location = urlsplit(response.headers["location"])
    assert (location.scheme, location.netloc) == ("http", "s3.localhost:8080")
    assert location.path == f"/artifacts/{stored.key}"
    query = parse_qs(location.query)
    assert query["response-content-disposition"] == [
        f'attachment; filename="{submission_id}-sim_run.fst"'
    ]
    assert query["response-content-type"] == ["application/octet-stream"]


def test_a_failed_recording_can_be_asked_again(
    api: TestClient, database_url: str, queue: RecordingQueue
) -> None:
    submission_id = failed_run(api, database_url, fst_expires=datetime.now(UTC))
    request(api, submission_id)
    [(_, job)] = queue.waveforms
    failed = WaveformRecord(
        submission_id=submission_id,
        token=job.check.token,
        waveform_id=job.waveform_id,
        artifact=None,
        error_code="TRACE_NOT_REPRODUCED",
    )
    record(database_url, failed)
    assert artifacts(api, submission_id)[-1]["state"] == "failed"
    assert request(api, submission_id).json()["state"] == "pending"
    assert len(queue.waveforms) == 2

    async def rows(database: Database) -> list[tuple[str, str | None]]:
        async with database.sessions() as session:
            found = await session.scalars(
                select(Waveform)
                .where(Waveform.submission_id == submission_id)
                .order_by(Waveform.created_at)
            )
            return [(w.status, w.error_code) for w in found]

    assert run(database_url, rows) == [("failed", "TRACE_NOT_REPRODUCED"), ("pending", None)]


def test_the_waveform_quota_of_a_guest(
    api: TestClient, database_url: str, queue: RecordingQueue
) -> None:
    submission_id = failed_run(api, database_url, fst_expires=datetime.now(UTC))

    async def fail_all(database: Database) -> None:
        async with database.sessions.begin() as session:
            await session.execute(update(Waveform).values(status="failed"))

    for _ in range(5):
        assert request(api, submission_id).status_code == 202
        run(database_url, fail_all)
    response = request(api, submission_id)
    assert response.status_code == 429
    assert response.json()["params"]["quota"] == "waveforms"
    assert len(queue.waveforms) == 5


def test_an_unavailable_queue_fails_the_recording(
    api: TestClient, database_url: str, queue: RecordingQueue
) -> None:
    submission_id = failed_run(api, database_url, fst_expires=datetime.now(UTC))
    queue.unavailable = True
    response = request(api, submission_id)
    assert response.status_code == 503
    assert response.json()["code"] == "JUDGE_UNAVAILABLE"
    assert artifacts(api, submission_id)[-1]["state"] == "failed"


def test_what_cannot_be_recorded(api: TestClient, database_url: str) -> None:
    submission_id = failed_run(api, database_url, fst_expires=None)
    full = request(api, submission_id, scope="full_test", test="t2")
    assert full.status_code == 401
    assert full.json()["code"] == "UNAUTHENTICATED"
    # No trace window: still running, or nothing was traced.
    running = uuid.UUID(submit(api).json()["id"])
    assert request(api, running).status_code == 404

    async def untraced(database: Database) -> None:
        async with database.sessions.begin() as session:
            await session.execute(
                update(StageResult)
                .where(StageResult.submission_id == submission_id)
                .values(metrics={"trace": "nondeterministic"})
            )

    run(database_url, untraced)
    assert request(api, submission_id).status_code == 404
    api.cookies.clear()  # another guest
    assert request(api, running).status_code == 404


def test_downloads(api: TestClient, database_url: str) -> None:
    submission_id = failed_run(api, database_url, fst_expires=datetime.now(UTC))
    base = f"/api/v1/submissions/{submission_id}/artifacts"

    def status(path: str) -> int:
        return api.get(f"{base}/{path}", follow_redirects=False).status_code

    assert status("log?stage=sim_run") == 302
    assert status("events") == 302
    assert status("fst?stage=sim_run") == 404  # expired
    assert status("log") == 404  # every log has a stage
    assert status("tb_result?stage=sim_run") == 422  # never offered
    location = api.get(f"{base}/log?stage=sim_run", follow_redirects=False).headers["location"]
    assert (
        f'filename="{submission_id}-sim_run.log.zst"'
        in parse_qs(urlsplit(location).query)["response-content-disposition"][0]
    )
    api.cookies.clear()  # another guest
    assert status("events") == 404
