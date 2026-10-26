"""The worker on a real broker: queues, slots, no retries, queue positions (specs/07 §3)."""

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from dramatiq import Message
from dramatiq.brokers.redis import RedisBroker

from apparatica_worker.broker import Handler
from apparatica_worker.main import create_workers, run
from apparatica_worker.settings import WorkerSettings
from judge.core.jobs import ACTOR, QUEUES, JudgeJob


def job() -> JudgeJob:
    return JudgeJob(
        submission_id=uuid.uuid4(),
        token="v1.token",
        problem="mux4",
        version=1,
        package_uri="mux4/1-abc.tar.zst",
        content_hash="abc",
        resource_class="light",
        kind="run",
        seed=1,
        code="module mux4; endmodule\n",
        toolchain_profile="sv-2026.10.2",
        toolchain_image="ghcr.io/apparatica/toolchain@sha256:" + "a" * 64,
    )


def send(url: str, queue: str, payload: JudgeJob, submission_id: str | None = None) -> None:
    """As the API sends a job (apparatica.submissions.queue)."""
    broker = RedisBroker(url=url, middleware=[])
    broker.declare_queue(queue)
    args = (submission_id or str(payload.submission_id), payload.model_dump(mode="json"))
    broker.enqueue(Message(queue_name=queue, actor_name=ACTOR, args=args, kwargs={}, options={}))
    broker.close()


def wait_for(condition: Callable[[], bool], timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.05)


@contextmanager
def worker(url: str, handler: Handler, **settings: Any) -> Iterator[None]:
    stop = threading.Event()
    thread = threading.Thread(
        target=run, args=(WorkerSettings(queue_url=url, **settings), stop, handler)
    )
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(30)


def test_the_worker_serves_every_queue(valkey_url: str) -> None:
    taken: list[tuple[uuid.UUID, str]] = []
    jobs = {queue: job() for queue in QUEUES}
    with worker(valkey_url, lambda j, q: taken.append((j.submission_id, q)), slots=1):
        for queue, payload in jobs.items():
            send(valkey_url, queue, payload)
        wait_for(lambda: len(taken) == len(QUEUES))
    assert sorted(taken, key=str) == sorted(
        ((payload.submission_id, queue) for queue, payload in jobs.items()), key=str
    )


def test_rejudges_have_their_own_slots(valkey_url: str) -> None:
    release = threading.Event()
    running: list[str] = []
    lock = threading.Lock()

    def slow(payload: JudgeJob, queue: str) -> None:
        with lock:
            running.append(queue)
        release.wait(30)

    with worker(valkey_url, slow, slots=2, rejudge_slots=1):
        for queue in ("judge.rejudge", "judge.rejudge", "judge.light", "judge.light"):
            send(valkey_url, queue, job())
        wait_for(lambda: len(running) == 3)
        time.sleep(0.5)  # a fourth check would have started by now
        # Two main slots and one rejudge slot: the second rejudge waits for the rejudge slot.
        assert sorted(running) == ["judge.light", "judge.light", "judge.rejudge"]
        release.set()
        wait_for(lambda: len(running) == 4)


def test_a_broken_message_is_not_retried(valkey_url: str) -> None:
    taken: list[uuid.UUID] = []
    good, broken = job(), job()
    with worker(valkey_url, lambda j, q: taken.append(j.submission_id), slots=1):
        send(valkey_url, "judge.light", broken, submission_id=str(uuid.uuid4()))
        send(valkey_url, "judge.light", good)
        wait_for(lambda: taken == [good.submission_id])
        time.sleep(0.5)
    assert taken == [good.submission_id]


def test_a_worker_holds_no_more_messages_than_it_runs() -> None:
    broker = RedisBroker(url="redis://127.0.0.1:1/0", middleware=[])
    settings = WorkerSettings(slots=3, rejudge_slots=2, queues=["judge.heavy"])
    main, rejudge = create_workers(broker, settings)
    assert (main.consumer_whitelist, main.queue_prefetch) == ({"judge.heavy"}, 3)
    assert (rejudge.consumer_whitelist, rejudge.queue_prefetch) == ({"judge.rejudge"}, 2)
    assert len(create_workers(broker, settings.model_copy(update={"rejudge_slots": 0}))) == 1
