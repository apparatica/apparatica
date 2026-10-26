"""Submissions without workers (specs/05 §3, phase 0) on Postgres with the repository problems."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from apparatica.core.db import Database
from apparatica.core.settings import Settings
from apparatica.main import create_app
from apparatica.submissions.models import Artifact, StageResult, Submission, ToolchainProfile
from apparatica.submissions.profiles import ProfileSpec, add_profile
from apparatica.submissions.queue import Job, QueueUnavailableError
from conftest import CONFIG_DIR, PROBLEMS, Postgres

PROBLEM = "application/problem+json"
PROFILE = ProfileSpec(
    id="sv-2026.10.2",
    language="systemverilog",
    image="ghcr.io/apparatica/toolchain",
    image_digest="sha256:" + "a" * 64,
    tools={"verilator": "5.052"},
    normalization_version=1,
)
CODE = (PROBLEMS / "mux4" / "reference" / "mux4.sv").read_text(encoding="utf-8")


class RecordingQueue:
    """Jobs in the order they were queued; none is ever taken."""

    def __init__(self) -> None:
        self.jobs: list[Job] = []
        self.unavailable = False

    async def enqueue(self, job: Job) -> None:
        if self.unavailable:
            raise QueueUnavailableError("connection refused")
        self.jobs.append(job)

    async def position(self, queue: str, submission_id: uuid.UUID) -> int | None:
        waiting = [job.submission_id for job in self.jobs if job.queue == queue]
        return waiting.index(submission_id) + 1 if submission_id in waiting else None

    async def close(self) -> None:
        pass


def run(url: str, scenario: Any) -> Any:
    async def main() -> Any:
        database = Database(url)
        try:
            return await scenario(database)
        finally:
            await database.dispose()

    return asyncio.run(main())


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
def queue() -> RecordingQueue:
    return RecordingQueue()


@pytest.fixture
def api(database_url: str, queue: RecordingQueue) -> Iterator[TestClient]:
    settings = Settings(environment="test", database_url=database_url, config_dir=CONFIG_DIR)
    with TestClient(create_app(settings, job_queue=queue), raise_server_exceptions=False) as client:
        yield client


def submit(api: TestClient, **fields: Any) -> Any:
    body = {"problem": "mux4", "version": 1, "kind": "run", "code": CODE} | fields
    return api.post("/api/v1/submissions", json=body)


def test_a_submission_is_queued(api: TestClient, queue: RecordingQueue) -> None:
    response = submit(api, kind="submit")
    assert response.status_code == 202, response.text
    assert response.headers["cache-control"] == "private, no-store"
    body = response.json()
    assert response.headers["location"] == f"http://testserver/api/v1/submissions/{body['id']}"
    assert uuid.UUID(body["id"]).version == 7
    assert 0 <= int(body["seed"]) < 2**63
    assert {key: body[key] for key in body if key not in {"id", "seed", "created_at"}} == {
        "problem": "mux4",
        "problem_title": "Мультиплексор 4:1",
        "version": 1,
        "kind": "submit",
        "status": "queued",
        "code": CODE,
        "toolchain_profile": "sv-2026.10.2",
        "queue_position": 1,
        "eta_s": None,
        "started_at": None,
        "finished_at": None,
        "verdict_detail": None,
        "stages": [],
        "artifacts": [],
        "quota": None,
    }

    [job] = queue.jobs
    assert (job.submission_id, job.queue) == (uuid.UUID(body["id"]), "judge.light")
    payload = job.payload
    tokens = api.app.state.job_tokens  # type: ignore[attr-defined]
    assert tokens.verify(payload.token, job.submission_id).attempt_max == 2
    # Everything the worker needs: it has no access to the database.
    assert (payload.problem, payload.version, payload.kind, payload.code) == (
        "mux4",
        1,
        "submit",
        CODE,
    )
    assert str(payload.seed) == body["seed"]
    assert payload.package_uri.startswith("mux4/1-")
    assert payload.resource_class == "light"
    assert payload.toolchain_image == f"{PROFILE.image}@{PROFILE.image_digest}"

    stored = api.get(f"/api/v1/submissions/{body['id']}")
    assert stored.status_code == 200
    assert stored.headers["cache-control"] == "private, no-store"
    assert stored.json() == {key: body[key] for key in body if key != "quota"}
    # Every submission has its own seed.
    assert submit(api).json()["seed"] != body["seed"]


def test_a_submission_waits_in_its_queue(api: TestClient) -> None:
    first, second = submit(api).json(), submit(api).json()
    assert (first["queue_position"], second["queue_position"]) == (1, 2)
    assert api.get(f"/api/v1/submissions/{second['id']}").json()["queue_position"] == 2


def test_an_unavailable_queue_fails_the_submission(
    api: TestClient, queue: RecordingQueue, database_url: str
) -> None:
    queue.unavailable = True
    response = submit(api)
    assert response.status_code == 503
    assert response.json()["code"] == "JUDGE_UNAVAILABLE"

    async def stored(database: Database) -> Submission:
        async with database.sessions() as session:
            return (await session.scalars(select(Submission))).one()

    # It would wait forever otherwise: the submission is stored as failed.
    submission = run(database_url, stored)
    assert submission.status == "internal_error"
    assert submission.verdict_detail is not None
    assert submission.verdict_detail["error_codes"] == ["QUEUE_UNAVAILABLE"]
    assert submission.finished_at is not None


def test_submissions_check_the_current_version(api: TestClient, database_url: str) -> None:
    outdated = submit(api, version=2)
    assert outdated.status_code == 409
    assert outdated.headers["content-type"] == PROBLEM
    assert outdated.json()["code"] == "PROBLEM_VERSION_OUTDATED"
    assert outdated.json()["params"] == {"current_version": 1}
    assert submit(api, problem="no-such-problem").json()["code"] == "NOT_FOUND"

    async def no_default(database: Database) -> None:
        async with database.sessions.begin() as session:
            await session.execute(update(ToolchainProfile).values(is_default=False))

    run(database_url, no_default)
    unavailable = submit(api)
    assert unavailable.status_code == 503
    assert unavailable.json()["code"] == "JUDGE_UNAVAILABLE"


@pytest.mark.parametrize(
    ("code", "size"),
    [
        ("x" * 65_537, {"bytes": 65_537, "lines": 1}),
        ("ж" * 32_769, {"bytes": 65_538, "lines": 1}),  # bytes of UTF-8, not characters
        ("\n" * 2_001, {"bytes": 2_001, "lines": 2_001}),
        ("x\n" * 2_000 + "x", {"bytes": 4_001, "lines": 2_001}),
    ],
    ids=["bytes", "utf-8-bytes", "empty-lines", "lines"],  # Windows limits PYTEST_CURRENT_TEST
)
def test_the_size_of_a_solution_is_limited(
    api: TestClient, queue: RecordingQueue, code: str, size: dict[str, int]
) -> None:
    response = submit(api, code=code)
    assert response.status_code == 413
    assert response.json()["code"] == "CODE_TOO_LARGE"
    assert response.json()["params"] == {"max_bytes": 65_536, "max_lines": 2_000} | size
    assert queue.jobs == []


def test_a_solution_at_the_limits_is_accepted(api: TestClient) -> None:
    assert submit(api, code="x\n" * 2_000).status_code == 202
    assert submit(api, code="x" * 65_536).status_code == 202


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "practice"},
        {"code": ""},
        {"code": "module m;\x00endmodule"},
        {"problem": "Mux_4"},
        {"version": 0},
        {"code": None},
    ],
)
def test_bad_requests(api: TestClient, fields: dict[str, Any]) -> None:
    response = submit(api, **fields)
    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_code_must_be_unicode_text(api: TestClient) -> None:
    # A lone surrogate is valid JSON but not UTF-8 text: the client library cannot send it.
    body = '{"problem": "mux4", "version": 1, "kind": "run", "code": "module \\ud800;"}'
    response = api.post(
        "/api/v1/submissions", content=body, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_unknown_submissions(api: TestClient) -> None:
    missing = api.get(f"/api/v1/submissions/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["code"] == "NOT_FOUND"
    assert api.get("/api/v1/submissions/not-an-id").status_code == 422


def test_a_finished_submission(api: TestClient, database_url: str) -> None:
    submission_id = uuid.UUID(submit(api, kind="submit").json()["id"])
    now = datetime.now(UTC)

    async def finish(database: Database) -> None:
        async with database.sessions.begin() as session:
            await session.execute(
                update(Submission)
                .where(Submission.id == submission_id)
                .values(
                    status="wrong_answer",
                    started_at=now,
                    finished_at=now,
                    verdict_detail={"first_failure": {"stage": "sim_full", "test": "hidden-1"}},
                )
            )
            # Stored out of order: the response follows the pipeline order.
            for ordinal, key, status in [
                (2, "sim_full", "failed"),
                (0, "precheck", "passed"),
                (1, "lint", "passed"),
            ]:
                session.add(
                    StageResult(
                        submission_id=submission_id,
                        stage_key=key,
                        stage_type=key.removesuffix("_full"),
                        ordinal=ordinal,
                        status=status,
                        failure_kind="wrong" if status == "failed" else None,
                        duration_ms=10,
                        metrics={"tests_total": 4} if key == "sim_full" else {},
                        metrics_schema="sim/v1" if key == "sim_full" else None,
                        summary={"hidden_tests": {"total": 2, "passed": 1, "failed_index": 1}}
                        if key == "sim_full"
                        else {},
                    )
                )
            for kind, expires_at in (
                ("log", None),
                ("fst", now - timedelta(days=1)),
                ("tb_result", None),
            ):
                session.add(
                    Artifact(
                        submission_id=submission_id,
                        stage_key="sim_full",
                        kind=kind,
                        storage_key=f"{submission_id}/{kind}",
                        size_bytes=100,
                        sha256="0" * 64,
                        expires_at=expires_at,
                    )
                )

    run(database_url, finish)
    body = api.get(f"/api/v1/submissions/{submission_id}").json()
    assert body["status"] == "wrong_answer"
    assert body["verdict_detail"] == {
        "first_failure": {"stage": "sim_full", "test": "hidden-1", "cycle": None},
        "limit": None,
        "warnings": [],
        "error_codes": [],
    }
    assert [(stage["key"], stage["status"]) for stage in body["stages"]] == [
        ("precheck", "passed"),
        ("lint", "passed"),
        ("sim_full", "failed"),
    ]
    sim = body["stages"][2]
    assert (sim["type"], sim["failure_kind"], sim["metrics"]) == (
        "sim",
        "wrong",
        {"tests_total": 4},
    )
    assert sim["summary"]["hidden_tests"] == {"total": 2, "passed": 1, "failed_index": 1}
    assert sim["summary"]["tests"] == []
    # The testbench result file holds hidden expected values: never listed (specs/07 §4.4).
    common = {"stage": "sim_full", "size_bytes": 100, "waveform": None}
    assert body["artifacts"] == [
        {"kind": "fst", "state": "expired", **common},
        {"kind": "log", "state": "ready", **common},
    ]
