"""The users of valkey-queue (deploy/valkey/queue-users.acl.in): the API and the worker do their
work with them and nothing else (specs/07 §5.3)."""

import os
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self

import boto3
import pytest
import redis
from dramatiq import Message
from dramatiq.brokers.redis import RedisBroker
from moto import mock_aws
from testcontainers.community.redis import RedisContainer

from apparatica_worker.main import run
from apparatica_worker.orchestrator import Orchestrator
from apparatica_worker.report import SANDBOX_UNAVAILABLE, AttemptReport
from apparatica_worker.settings import WorkerSettings
from apparatica_worker.storage import ArtifactStore, PackageCache
from judge.core.executor import ExecutorError
from judge.core.jobs import ACTOR, JudgeJob, position_key
from judge.core.limits import SandboxLimits, load_resource_classes
from judge.core.pack import content_hash, pack, package_files
from judge.core.stage import ExecResult

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

ROOT = Path(__file__).parents[2]
TEMPLATE = ROOT / "deploy" / "valkey" / "queue-users.acl.in"
VALKEY_IMAGE = os.environ.get("APX_TEST_VALKEY_IMAGE", "valkey/valkey:8-alpine")
PASSWORDS = {"API_PASSWORD": "api-secret", "WORKER_PASSWORD": "worker-secret"}


def acl_arguments() -> list[str]:
    """The directives of the template as valkey-server arguments, as start-queue.sh renders them."""
    arguments = []
    for line in TEMPLATE.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        for name, value in PASSWORDS.items():
            line = line.replace(f"@{name}@", value)
        keyword, *rule = line.split()
        arguments += [f"--{keyword}", *rule]
    return arguments


@pytest.fixture(scope="module")
def server() -> Iterator[tuple[str, str]]:
    """URLs of the api and worker users."""
    container = RedisContainer(VALKEY_IMAGE).with_command(["valkey-server", *acl_arguments()])
    try:
        container.start()
    except Exception as error:
        if os.environ.get("CI"):
            raise
        pytest.skip(f"Valkey tests need Docker: {error!r}")
    try:
        address = f"{container.get_container_host_ip()}:{container.get_exposed_port(6379)}"
        api = f"redis://api:{PASSWORDS['API_PASSWORD']}@{address}/0"
        worker = f"redis://worker:{PASSWORDS['WORKER_PASSWORD']}@{address}/0"
        yield api, worker
    finally:
        container.stop()


class NoSandbox:
    def __init__(self, job: JudgeJob, limits: SandboxLimits) -> None:
        pass

    def __enter__(self) -> Self:
        raise ExecutorError("no sandbox in this test")

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        pass

    def run(self, *args: Any, **kwargs: Any) -> ExecResult:
        raise AssertionError("never runs")


def test_the_users_do_their_work(server: tuple[str, str], tmp_path: Path) -> None:
    api_url, worker_url = server
    files = package_files(ROOT / "problems" / "mux4")
    job = JudgeJob(
        submission_id=uuid.uuid4(),
        token="v1.token",
        problem="mux4",
        version=1,
        package_uri="mux4/1.tar.zst",
        content_hash=content_hash(files),
        resource_class="light",
        kind="run",
        seed=1,
        code="module mux4; endmodule\n",
        toolchain_profile="sv-dev",
        toolchain_image="apparatica-toolchain:dev",
    )
    # The API, as apparatica.submissions.queue.DramatiqQueue does it.
    api = redis.Redis.from_url(api_url)
    api.zadd(position_key("judge.light"), {str(job.submission_id): time.time()})
    broker = RedisBroker(url=api_url, middleware=[])
    broker.declare_queue("judge.light")
    args = (str(job.submission_id), job.model_dump(mode="json"))
    broker.enqueue(
        Message(queue_name="judge.light", actor_name=ACTOR, args=args, kwargs={}, options={})
    )
    broker.close()

    reports: list[AttemptReport] = []
    with mock_aws():
        s3: S3Client = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="packages")
        s3.put_object(Bucket="packages", Key="mux4/1.tar.zst", Body=pack(files))
        orchestrator = Orchestrator(
            valkey=redis.Redis.from_url(worker_url),
            packages=PackageCache(s3, "packages", tmp_path),
            artifacts=ArtifactStore(s3, "artifacts"),
            executor=NoSandbox,
            classes=load_resource_classes(ROOT / "config" / "resource-classes.yaml"),
            reporter=type("Reports", (), {"report": lambda self, r: reports.append(r)})(),
            owner="worker-acl",
        )
        stop = threading.Event()
        settings = WorkerSettings(queue_url=worker_url, slots=1, rejudge_slots=1)
        thread = threading.Thread(target=run, args=(settings, stop, orchestrator))
        thread.start()
        try:
            deadline = time.monotonic() + 20
            while not reports and time.monotonic() < deadline:
                time.sleep(0.1)
        finally:
            stop.set()
            thread.join(30)
    # The worker took the job, its position, its lease and its attempt; only the sandbox failed.
    assert [(r.attempt, r.error_code) for r in reports] == [(1, SANDBOX_UNAVAILABLE)]
    assert api.zrank(position_key("judge.light"), str(job.submission_id)) is None


@pytest.mark.parametrize(
    ("user", "command"),
    [
        ("worker", lambda r: r.set("session:1", "x")),  # keys of no component
        ("worker", lambda r: r.zrank("queue:judge.light", "x")),  # positions: remove only
        ("worker", lambda r: r.flushall()),
        ("worker", lambda r: r.keys("*")),
        ("worker", lambda r: r.config_get("*")),
        ("api", lambda r: r.set("lease:1", "x")),
        ("api", lambda r: r.incr("attempts:1")),
        ("default", lambda r: r.get("queue:judge.light")),
    ],
    ids=[
        "other-key",
        "read-position",
        "flushall",
        "keys",
        "config",
        "lease",
        "attempts",
        "default",
    ],
)
def test_the_users_do_nothing_else(
    server: tuple[str, str], user: str, command: Callable[[redis.Redis], object]
) -> None:
    api_url, worker_url = server
    anonymous = "redis://" + api_url.split("@", 1)[1]  # the default user, as the health check
    url = {"api": api_url, "worker": worker_url, "default": anonymous}[user]
    with pytest.raises(redis.exceptions.NoPermissionError):
        command(redis.Redis.from_url(url))
