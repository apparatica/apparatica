"""A whole attempt: Valkey, the package from S3 (moto), apx-sandboxd with Docker and the toolchain
image, the pipeline of the judge, the artifacts. Marked `image`: run by `just toolchain-test`."""

import asyncio
import io
import json
import os
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import boto3
import pytest
import redis
import zstandard
from moto import mock_aws
from stream_helpers import read_stream

from apparatica_worker.cancel import CancelListener
from apparatica_worker.orchestrator import Orchestrator
from apparatica_worker.report import AttemptReport
from apparatica_worker.sandboxd.client import SandboxdClient, SandboxExecutor
from apparatica_worker.sandboxd.server import MAX_REQUEST, DockerCli, Policy, Sandboxd, repository
from apparatica_worker.storage import ArtifactStore, PackageCache
from apparatica_worker.stream import ResultsStream
from judge.core.jobs import (
    CANCEL_CHANNEL,
    CANCEL_NOTES,
    RESULT_RECORD,
    RESULTS_STREAM,
    JudgeJob,
    StageEndRecord,
    cancel_key,
    lease_key,
    submission_stream_key,
)
from judge.core.limits import SandboxLimits, load_resource_classes
from judge.core.pack import content_hash, pack, package_files

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

pytestmark = pytest.mark.image

ROOT = Path(__file__).parents[2]
IMAGE = os.environ.get("TOOLCHAIN_IMAGE", "apparatica-toolchain:dev")
RUNTIME = os.environ.get("JUDGE_SANDBOX_RUNTIME", "runc")


class Reports:
    def __init__(self) -> None:
        self.items: list[AttemptReport] = []

    def report(self, report: AttemptReport) -> None:
        self.items.append(report)


@pytest.fixture(scope="module")
def sandboxd() -> Iterator[SandboxdClient]:
    policy = Policy(RUNTIME, frozenset({repository(IMAGE)}), SandboxLimits(4, 8192, 256), 4, 3600)
    daemon = Sandboxd(policy, DockerCli())
    loop = asyncio.new_event_loop()
    server = loop.run_until_complete(
        asyncio.start_server(daemon.handle, "127.0.0.1", 0, limit=MAX_REQUEST)
    )
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    yield SandboxdClient(("127.0.0.1", server.sockets[0].getsockname()[1]))
    loop.call_soon_threadsafe(loop.stop)
    thread.join()
    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()


@pytest.fixture
def s3() -> Iterator["S3Client"]:
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="packages")
        client.create_bucket(Bucket="artifacts")
        yield client


def attempt(
    sandboxd: SandboxdClient,
    s3: "S3Client",
    valkey_url: str,
    tmp_path: Path,
    slug: str,
    code: str,
    cancel_after_s: float | None = None,
) -> AttemptReport:
    files = package_files(ROOT / "problems" / slug)
    s3.put_object(Bucket="packages", Key=f"{slug}/1.tar.zst", Body=pack(files))
    job = JudgeJob(
        submission_id=uuid.UUID(int=(time.time_ns() // 1_000_000 << 80) | (7 << 76) | (2 << 62)),
        token="v1.token",
        problem=slug,
        version=1,
        package_uri=f"{slug}/1.tar.zst",
        content_hash=content_hash(files),
        resource_class="light",
        kind="run",
        seed=42,
        code=code,
        toolchain_profile="sv-dev",
        toolchain_image=IMAGE,
    )
    reports = Reports()
    valkey = redis.Redis.from_url(valkey_url)
    orchestrator = Orchestrator(
        valkey=valkey,
        packages=PackageCache(s3, "packages", tmp_path),
        artifacts=ArtifactStore(s3, "artifacts"),
        executor=lambda job, limits: SandboxExecutor(sandboxd, job.toolchain_image, limits),
        classes=load_resource_classes(ROOT / "config" / "resource-classes.yaml"),
        results=ResultsStream(valkey),
        reporter=reports,
        owner="worker-test",
    )
    if cancel_after_s is None:
        orchestrator(job, "judge.light")
    else:  # as the API does it: the key, then the message
        orchestrator.cancels = CancelListener(valkey)
        orchestrator.cancels.start()

        def cancel() -> None:
            valkey.set(cancel_key(job.submission_id), "user")
            valkey.publish(CANCEL_CHANNEL, f"{job.submission_id} user")

        timer = threading.Timer(cancel_after_s, cancel)
        timer.start()
        try:
            orchestrator(job, "judge.light")
        finally:
            timer.cancel()
            orchestrator.cancels.stop()
    [report] = reports.items
    assert orchestrator.valkey.get(lease_key(job.submission_id)) is None
    return report


def read(s3: "S3Client", key: str) -> bytes:
    return s3.get_object(Bucket="artifacts", Key=key)["Body"].read()


def test_an_accepted_run(
    sandboxd: SandboxdClient, s3: "S3Client", valkey_url: str, tmp_path: Path
) -> None:
    code = (ROOT / "problems" / "mux4" / "reference" / "mux4.sv").read_text(encoding="utf-8")
    report = attempt(sandboxd, s3, valkey_url, tmp_path, "mux4", code)
    assert report.error_code is None
    assert [(r.key, r.status) for r in report.results] == [
        ("precheck", "passed"),
        ("lint", "passed"),
        ("sim_run", "passed"),
    ]
    kinds = {(a.kind, a.stage) for a in report.artifacts}
    assert {("log", "precheck"), ("log", "lint"), ("log", "sim_run"), ("events", None)} <= kinds
    events = zstandard.ZstdDecompressor().decompress(
        read(s3, next(a.key for a in report.artifacts if a.kind == "events"))
    )
    journal = [json.loads(line) for line in io.BytesIO(events)]
    assert journal[-1]["event"] == {"type": "done", "attempt": 1}
    # The browser saw the same events under the same ids.
    valkey = redis.Redis.from_url(valkey_url)
    stream = read_stream(valkey, submission_stream_key(report.job.submission_id))
    assert [(r["id"], r["event"]) for r in journal] == stream
    logs = [r["event"] for r in journal if r["event"]["type"] == "log"]
    assert logs
    assert all(log["text"].endswith("\n") for log in logs)
    # The ingestor got each stage result as it ended, with the job token.
    records = [RESULT_RECORD.validate_python(r) for _, r in read_stream(valkey, RESULTS_STREAM)]
    assert records[0].type == "attempt_started"
    assert [(r.result.key, r.token) for r in records if isinstance(r, StageEndRecord)] == [
        ("precheck", "v1.token"),
        ("lint", "v1.token"),
        ("sim_run", "v1.token"),
    ]


def test_a_cancel_kills_the_running_stage(
    sandboxd: SandboxdClient, s3: "S3Client", valkey_url: str, tmp_path: Path
) -> None:
    code = (ROOT / "problems" / "sync-fifo" / "reference" / "sync_fifo.sv").read_text("utf-8")
    started = time.monotonic()
    report = attempt(sandboxd, s3, valkey_url, tmp_path, "sync-fifo", code, cancel_after_s=3)
    assert report.cancelled
    assert time.monotonic() - started < 60  # not the whole check
    statuses = [r.status for r in report.results]
    assert "cancelled" in statuses
    assert set(statuses[statuses.index("cancelled") + 1 :]) <= {"skipped"}
    cancelled = next(r for r in report.results if r.status == "cancelled")
    log = zstandard.ZstdDecompressor().decompress(
        read(s3, next(a.key for a in report.artifacts if a.stage == cancelled.key))
    )
    assert log.decode().splitlines()[-1] == CANCEL_NOTES["user"]


def test_a_wrong_answer_keeps_its_trace(
    sandboxd: SandboxdClient, s3: "S3Client", valkey_url: str, tmp_path: Path
) -> None:
    mutant = ROOT / "problems" / "sync-fifo" / "mutants" / "m01_full_off_by_one.sv"
    report = attempt(sandboxd, s3, valkey_url, tmp_path, "sync-fifo", mutant.read_text("utf-8"))
    sim = report.results[-1]
    assert (sim.key, sim.status, sim.failure_kind) == ("sim_run", "failed", "wrong")
    [trace] = [a for a in report.artifacts if a.kind == "fst"]
    assert trace.stage == "sim_run"
    assert trace.key.endswith("/1/sim_run/trace.fst")
    data = read(s3, trace.key)
    assert data
    assert trace.size_bytes == len(data)
    assert any(a.kind == "tb_result" for a in report.artifacts)
