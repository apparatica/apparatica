"""The orchestrator without a sandbox: lease, attempts, the package cache, artifacts (specs/07 §3).
The pipeline in a real sandbox: test_orchestrator_image.py."""

import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, ClassVar, Self

import boto3
import pytest
import redis
from moto import mock_aws
from stream_helpers import read_stream

from apparatica_worker.lease import Lease
from apparatica_worker.orchestrator import Orchestrator
from apparatica_worker.report import (
    ATTEMPTS_EXHAUSTED,
    PACKAGE_UNAVAILABLE,
    SANDBOX_UNAVAILABLE,
    AttemptReport,
    StreamReporter,
)
from apparatica_worker.storage import ArtifactStore, PackageCache, PackageError, artifact_key
from apparatica_worker.stream import ResultsStream
from judge.core.executor import ExecutorError
from judge.core.jobs import (
    RESULT_RECORD,
    RESULTS_STREAM,
    AttemptFailedRecord,
    AttemptStartedRecord,
    JudgeJob,
    attempts_key,
    lease_key,
    position_key,
)
from judge.core.limits import SandboxLimits, load_resource_classes
from judge.core.pack import content_hash, pack, package_files
from judge.core.stage import ExecResult

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

ROOT = Path(__file__).parents[2]
MUX4 = ROOT / "problems" / "mux4"
CLASSES = load_resource_classes(ROOT / "config" / "resource-classes.yaml")


class Reports:
    def __init__(self) -> None:
        self.items: list[AttemptReport] = []

    def report(self, report: AttemptReport) -> None:
        self.items.append(report)


class BrokenSandbox:
    """apx-sandboxd refuses: the attempt ends before the pipeline."""

    created: ClassVar[list[SandboxLimits]] = []

    def __init__(self, job: JudgeJob, limits: SandboxLimits) -> None:
        BrokenSandbox.created.append(limits)

    def __enter__(self) -> Self:
        raise ExecutorError("apx-sandboxd is unavailable: connection refused")

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        pass

    def run(self, *args: Any, **kwargs: Any) -> ExecResult:
        raise AssertionError("never runs")


@pytest.fixture
def s3() -> Iterator["S3Client"]:
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="packages")
        client.create_bucket(Bucket="artifacts")
        yield client


def job(**fields: Any) -> JudgeJob:
    files = package_files(MUX4)
    return JudgeJob.model_validate(
        {
            "submission_id": str(uuid.UUID(int=(1793003347000 << 80) | (7 << 76) | 1)),
            "token": "v1.token",
            "problem": "mux4",
            "version": 1,
            "package_uri": "mux4/1-abc.tar.zst",
            "content_hash": content_hash(files),
            "resource_class": "light",
            "kind": "run",
            "seed": 1,
            "code": "module mux4; endmodule\n",
            "toolchain_profile": "sv-2026.10.3",
            "toolchain_image": "apparatica-toolchain:dev",
        }
        | fields
    )


@pytest.fixture
def orchestrator(valkey_url: str, s3: "S3Client", tmp_path: Path) -> Orchestrator:
    s3.put_object(Bucket="packages", Key="mux4/1-abc.tar.zst", Body=pack(package_files(MUX4)))
    BrokenSandbox.created = []
    valkey = redis.Redis.from_url(valkey_url)
    return Orchestrator(
        valkey=valkey,
        packages=PackageCache(s3, "packages", tmp_path / "packages"),
        artifacts=ArtifactStore(s3, "artifacts"),
        executor=BrokenSandbox,
        classes=CLASSES,
        results=ResultsStream(valkey),
        reporter=Reports(),
        owner="worker-a",
    )


def reports(orchestrator: Orchestrator) -> list[AttemptReport]:
    assert isinstance(orchestrator.reporter, Reports)
    return orchestrator.reporter.items


def test_an_attempt_takes_the_job_off_the_queue(orchestrator: Orchestrator) -> None:
    payload = job()
    valkey = orchestrator.valkey
    valkey.zadd(position_key("judge.light"), {str(payload.submission_id): 1})
    orchestrator(payload, "judge.light")
    assert valkey.zrank(position_key("judge.light"), str(payload.submission_id)) is None
    [report] = reports(orchestrator)
    # The package came, the sandbox did not: no results, internal_error for the ingestor.
    assert (report.attempt, report.error_code, report.results) == (1, SANDBOX_UNAVAILABLE, ())
    assert BrokenSandbox.created == [SandboxLimits(cpus=2, memory_mb=2048, pids=256)]
    assert valkey.get(lease_key(payload.submission_id)) is None  # released
    assert int(valkey.get(attempts_key(payload.submission_id)) or 0) == 1
    assert valkey.ttl(attempts_key(payload.submission_id)) > 0


def test_a_failed_attempt_goes_to_the_ingestor(orchestrator: Orchestrator) -> None:
    orchestrator.reporter = StreamReporter(orchestrator.results)
    payload = job()
    orchestrator(payload, "judge.light")
    stream = read_stream(orchestrator.valkey, RESULTS_STREAM)
    records = [RESULT_RECORD.validate_python(record) for _, record in stream]
    common: dict[str, Any] = {
        "submission_id": payload.submission_id,
        "attempt": 1,
        "token": payload.token,
    }
    assert records == [
        AttemptStartedRecord(**common),
        AttemptFailedRecord(**common, error_code=SANDBOX_UNAVAILABLE),
    ]


def test_an_exhausted_check_does_not_start(orchestrator: Orchestrator) -> None:
    payload = job()
    orchestrator.valkey.set(attempts_key(payload.submission_id), 2)
    orchestrator(payload, "judge.light")
    assert read_stream(orchestrator.valkey, RESULTS_STREAM) == []  # no attempt_started
    assert [(r.attempt, r.error_code) for r in reports(orchestrator)] == [(3, ATTEMPTS_EXHAUSTED)]


def test_a_duplicate_message_is_dropped(orchestrator: Orchestrator) -> None:
    payload = job()
    orchestrator.valkey.set(lease_key(payload.submission_id), "worker-b", px=15000)
    orchestrator(payload, "judge.light")
    assert reports(orchestrator) == []
    assert orchestrator.valkey.get(attempts_key(payload.submission_id)) is None
    assert orchestrator.valkey.get(lease_key(payload.submission_id)) == b"worker-b"


def test_a_check_has_two_attempts(orchestrator: Orchestrator) -> None:
    payload = job()
    orchestrator(payload, "judge.light")
    orchestrator(payload, "judge.light")
    orchestrator(payload, "judge.light")
    assert [(r.attempt, r.error_code) for r in reports(orchestrator)] == [
        (1, SANDBOX_UNAVAILABLE),
        (2, SANDBOX_UNAVAILABLE),
        (3, ATTEMPTS_EXHAUSTED),
    ]
    assert len(BrokenSandbox.created) == 2  # the third attempt did not run


@pytest.mark.parametrize(
    "fields",
    [{"package_uri": "mux4/missing.tar.zst"}, {"content_hash": "0" * 64}],
)
def test_a_bad_package_fails_the_attempt(
    orchestrator: Orchestrator, fields: dict[str, str]
) -> None:
    orchestrator(job(**fields), "judge.light")
    [report] = reports(orchestrator)
    assert report.error_code == PACKAGE_UNAVAILABLE
    assert BrokenSandbox.created == []


def test_packages_are_cached_by_content(s3: "S3Client", tmp_path: Path) -> None:
    s3.put_object(Bucket="packages", Key="mux4/1-abc.tar.zst", Body=pack(package_files(MUX4)))
    cache = PackageCache(s3, "packages", tmp_path)
    path = cache.get(job())
    assert (path / "problem.yaml").read_bytes() == (MUX4 / "problem.yaml").read_bytes()
    assert (path.parent.name, path.name) == (job().content_hash, "mux4")
    s3.delete_object(Bucket="packages", Key="mux4/1-abc.tar.zst")
    assert cache.get(job()) == path  # no download any more
    assert [p.name for p in tmp_path.iterdir()] == [path.parent.name]  # no partial directories
    with pytest.raises(PackageError, match="cannot download"):
        cache.get(job(content_hash="1" * 64))


def test_artifact_keys_follow_the_submission(s3: "S3Client") -> None:
    payload = job()
    stored = ArtifactStore(s3, "artifacts").put(
        payload, 2, "fst", "sim_run", "sim_run/trace.fst", b"x"
    )
    assert stored.key == f"2026/10/{payload.submission_id}/2/sim_run/trace.fst"
    assert stored.key == artifact_key(payload.submission_id, 2, "sim_run/trace.fst")
    assert (stored.kind, stored.stage, stored.size_bytes) == ("fst", "sim_run", 1)
    assert s3.get_object(Bucket="artifacts", Key=stored.key)["Body"].read() == b"x"


def test_the_lease_is_renewed_and_lost(valkey_url: str) -> None:
    client = redis.Redis.from_url(valkey_url)
    submission = uuid.uuid4()
    with Lease(client, submission, "worker-a", ttl_s=0.5, renew_s=0.1) as lease:
        assert lease.held
        time.sleep(1)  # twice the TTL: alive only because it is renewed
        assert client.get(lease_key(submission)) == b"worker-a"
        with Lease(client, submission, "worker-b") as other:
            assert not other.held
        client.set(lease_key(submission), "worker-b")  # expired and taken meanwhile
        assert lease.lost.wait(2)
    assert client.get(lease_key(submission)) == b"worker-b"  # not released: it is not ours


def test_an_orchestrator_is_thread_safe_on_the_cache(s3: "S3Client", tmp_path: Path) -> None:
    s3.put_object(Bucket="packages", Key="mux4/1-abc.tar.zst", Body=pack(package_files(MUX4)))
    cache = PackageCache(s3, "packages", tmp_path)
    paths: list[Path] = []
    threads = [threading.Thread(target=lambda: paths.append(cache.get(job()))) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(set(paths)) == 1
