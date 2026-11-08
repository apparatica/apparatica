"""The users of valkey-queue (deploy/valkey/queue-users.acl.in): the API and the worker do their
work with them and nothing else (specs/07 §5.3)."""

import contextlib
import json
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
from dramatiq.brokers.redis import MAINTENANCE_SCALE, RedisBroker
from moto import mock_aws
from testcontainers.community.redis import RedisContainer

from apparatica_worker.main import run
from apparatica_worker.orchestrator import Orchestrator
from apparatica_worker.report import SANDBOX_UNAVAILABLE, AttemptReport, StreamReporter
from apparatica_worker.settings import WorkerSettings
from apparatica_worker.storage import ArtifactStore, PackageCache
from apparatica_worker.stream import ResultsStream, ValkeyStreamSink
from judge.core.events import DoneEvent
from judge.core.executor import ExecutorError
from judge.core.jobs import (
    ACTOR,
    RESULTS_STREAM,
    AttemptFailedRecord,
    JudgeJob,
    position_key,
    submission_stream_key,
)
from judge.core.limits import SandboxLimits, load_resource_classes
from judge.core.pack import content_hash, pack, package_files
from judge.core.stage import ExecResult

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

ROOT = Path(__file__).parents[2]
TEMPLATE = ROOT / "deploy" / "valkey" / "queue-users.acl.in"
VALKEY_IMAGE = os.environ.get("APX_TEST_VALKEY_IMAGE", "valkey/valkey:8-alpine")
PASSWORDS = {
    "API_PASSWORD": "api-secret",
    "WORKER_PASSWORD": "worker-secret",
    "INGEST_PASSWORD": "ingest-secret",
}


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
    worker = redis.Redis.from_url(worker_url)
    results = ResultsStream(worker, retries=1)
    reporter = StreamReporter(results)

    class Reports:
        def report(self, report: AttemptReport) -> None:
            reporter.report(report)
            reports.append(report)

    with mock_aws():
        s3: S3Client = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="packages")
        s3.put_object(Bucket="packages", Key="mux4/1.tar.zst", Body=pack(files))
        orchestrator = Orchestrator(
            valkey=worker,
            packages=PackageCache(s3, "packages", tmp_path),
            artifacts=ArtifactStore(s3, "artifacts"),
            executor=NoSandbox,
            classes=load_resource_classes(ROOT / "config" / "resource-classes.yaml"),
            results=results,
            reporter=Reports(),
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
    # It writes results and events; the streams are not its to read.
    assert results.write(
        AttemptFailedRecord(submission_id=job.submission_id, attempt=1, token="t", error_code="X")
    )
    with ValkeyStreamSink(worker, job, 1) as sink:
        sink.emit(DoneEvent())
    assert json.loads(sink.journal[0])["id"] is not None
    for read in (
        lambda: worker.xrange(RESULTS_STREAM),
        lambda: worker.xread({submission_stream_key(job.submission_id): 0}),
    ):
        with pytest.raises(redis.exceptions.NoPermissionError):
            read()


def test_the_worker_requeues_the_messages_of_a_dead_worker(server: tuple[str, str]) -> None:
    """The maintenance of the broker (ADR-0002) as the worker runs it, with KEYS; a sender with
    maintenance would fail the command it sends, so the senders have none."""
    api_url, worker_url = server
    queue = f"judge.maintenance-{uuid.uuid4().hex}"
    heartbeats = "dramatiq:__heartbeats__"

    def broker(url: str, *, maintenance: bool) -> RedisBroker:
        chance = MAINTENANCE_SCALE if maintenance else 0
        made = RedisBroker(url=url, middleware=[], maintenance_chance=chance)
        made.declare_queue(queue)
        return made

    sender = broker(api_url, maintenance=False)
    sent = sender.enqueue(
        Message(queue_name=queue, actor_name=ACTOR, args=(), kwargs={}, options={})
    )
    sender.close()
    # A worker takes the message and dies before the ack: its heartbeat is long gone.
    dead = broker(worker_url, maintenance=False)
    assert len(dead.do_fetch(queue, 1)) == 1
    worker = redis.Redis.from_url(worker_url)
    worker.zadd(heartbeats, {dead.broker_id: 0})
    dead.close()

    api = broker(api_url, maintenance=True)
    with pytest.raises(redis.exceptions.ResponseError, match="keys"):
        api.enqueue(Message(queue_name=queue, actor_name=ACTOR, args=(), kwargs={}, options={}))
    api.close()

    alive = broker(worker_url, maintenance=True)
    fetched = alive.do_fetch(queue, 1)
    alive.close()
    assert [Message.decode(data).message_id for data in fetched] == [sent.message_id]
    assert worker.zscore(heartbeats, dead.broker_id) is None


def ingest(api_url: str) -> str:
    """The URL of the ingest user on the same server."""
    return api_url.replace(
        f"api:{PASSWORDS['API_PASSWORD']}", f"ingest:{PASSWORDS['INGEST_PASSWORD']}"
    )


def test_the_ingestor_reads_results_and_writes_finalized(server: tuple[str, str]) -> None:
    api_url, worker_url = server
    redis.Redis.from_url(worker_url).xadd(RESULTS_STREAM, {"r": "{}"})
    client = redis.Redis.from_url(ingest(api_url))
    with contextlib.suppress(redis.exceptions.ResponseError):  # BUSYGROUP: an earlier run
        client.xgroup_create(RESULTS_STREAM, "ingest", id="0")
    entries: Any = client.xreadgroup("ingest", "ingest-acl", {RESULTS_STREAM: ">"})
    assert entries
    entry_id = entries[0][1][0][0]
    client.xack(RESULTS_STREAM, "ingest", entry_id)
    client.xdel(RESULTS_STREAM, entry_id)
    client.xadd("sub:1", {"e": "{}"})
    client.expire("sub:1", 600)
    client.set("leader:ingest", "ingest-acl", nx=True, px=30000)  # the leader of the instances
    client.exists("lease:1")  # the watchdog: does a worker hold the check
    # The metrics: checks waiting in each queue, the oldest of them, results not stored yet.
    client.zcard("queue:judge.light")
    client.zrange("queue:judge.light", 0, 0, withscores=True)
    client.xlen(RESULTS_STREAM)
    # The leader puts a run of a reference solution on judge.rejudge, as DramatiqQueue does it.
    run = str(uuid.uuid4())
    client.zadd(position_key("judge.rejudge"), {run: time.time()})
    broker = RedisBroker(url=ingest(api_url), middleware=[])
    broker.declare_queue("judge.rejudge")
    broker.enqueue(
        Message(queue_name="judge.rejudge", actor_name=ACTOR, args=(run,), kwargs={}, options={})
    )
    broker.close()
    assert redis.Redis.from_url(worker_url).llen("dramatiq:judge.rejudge") >= 1
    # The SSE endpoint of the API reads what the ingestor and the worker wrote.
    api = redis.Redis.from_url(api_url)
    assert api.xrange("sub:1")
    # A cancel: the API sets the key and publishes, the worker and the ingestor listen.
    for listener in (client, redis.Redis.from_url(worker_url)):
        pubsub: Any = listener.pubsub(ignore_subscribe_messages=True)  # type: ignore[no-untyped-call]
        pubsub.subscribe("judge:cancel")
        pubsub.close()
    api.set("cancel:1", "user", ex=60)
    api.publish("judge:cancel", "1 user")
    assert redis.Redis.from_url(worker_url).get("cancel:1") == b"user"


@pytest.mark.parametrize(
    ("user", "command"),
    [
        ("worker", lambda r: r.set("session:1", "x")),  # keys of no component
        ("worker", lambda r: r.zrank("queue:judge.light", "x")),  # positions: remove only
        ("worker", lambda r: r.flushall()),
        ("api", lambda r: r.keys("*")),  # KEYS is the worker's, for the maintenance
        ("ingest", lambda r: r.keys("*")),
        ("worker", lambda r: r.config_get("*")),
        ("api", lambda r: r.set("lease:1", "x")),
        ("api", lambda r: r.incr("attempts:1")),
        ("api", lambda r: r.xadd("judge:results", {"r": "{}"})),  # a forged result
        ("api", lambda r: r.xadd("sub:1", {"e": "{}"})),  # reads the events, writes none
        ("ingest", lambda r: r.xrange("sub:1")),  # writes finalized, reads no events
        ("ingest", lambda r: r.set("lease:1", "x")),  # reads leases, holds none
        ("ingest", lambda r: r.publish("judge:cancel", "x")),  # listens only
        ("worker", lambda r: r.publish("judge:cancel", "x")),
        ("worker", lambda r: r.set("cancel:1", "user")),  # reads cancels, makes none
        ("api", lambda r: r.get("cancel:1")),
        # Reads the positions of the queues, puts only reference runs on judge.rejudge.
        ("ingest", lambda r: r.zadd("queue:judge.light", {"x": 1})),
        ("default", lambda r: r.get("queue:judge.light")),
    ],
    ids=[
        "other-key",
        "read-position",
        "flushall",
        "api-keys",
        "ingest-keys",
        "config",
        "lease",
        "attempts",
        "results",
        "api-events",
        "ingest-events",
        "ingest-lease",
        "ingest-publish",
        "worker-publish",
        "worker-cancel",
        "api-read-cancel",
        "ingest-position",
        "default",
    ],
)
def test_the_users_do_nothing_else(
    server: tuple[str, str], user: str, command: Callable[[redis.Redis], object]
) -> None:
    api_url, worker_url = server
    anonymous = "redis://" + api_url.split("@", 1)[1]  # the default user, as the health check
    users = {"api": api_url, "worker": worker_url, "ingest": ingest(api_url), "default": anonymous}
    url = users[user]
    with pytest.raises(redis.exceptions.NoPermissionError):
        command(redis.Redis.from_url(url))
