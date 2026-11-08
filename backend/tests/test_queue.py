"""The queue of checks on Valkey: Dramatiq messages for the worker and queue positions."""

import asyncio
import random
import uuid

import pytest
import redis
from dramatiq.brokers.redis import RedisBroker

from apparatica.submissions.queue import DramatiqQueue, Job, QueueUnavailableError
from judge.core.jobs import ACTOR, JudgeJob, position_key


def job(queue: str = "judge.light") -> Job:
    payload = JudgeJob(
        submission_id=uuid.uuid4(),
        token="v1.token",
        problem="mux4",
        version=1,
        package_uri="mux4/1-abc.tar.zst",
        content_hash="abc",
        resource_class="light",
        kind="run",
        seed=2**63 - 1,
        code="module mux4; endmodule\n",
        toolchain_profile="sv-2026.10.2",
        toolchain_image="ghcr.io/apparatica/toolchain@sha256:" + "a" * 64,
    )
    return Job(queue=queue, payload=payload)


def test_a_job_is_a_message_of_the_worker_actor(valkey_url: str) -> None:
    first, second = job(), job()

    async def scenario() -> list[int | None]:
        queue = DramatiqQueue(valkey_url)
        try:
            await queue.enqueue(first)
            await queue.enqueue(second)
            return [
                await queue.position("judge.light", first.submission_id),
                await queue.position("judge.light", second.submission_id),
                await queue.position("judge.heavy", first.submission_id),
            ]
        finally:
            await queue.close()

    assert asyncio.run(scenario()) == [1, 2, None]
    # What a worker gets: the actor, the submission and the job with every field.
    consumer = RedisBroker(url=valkey_url, middleware=[]).consume(
        "judge.light", prefetch=2, timeout=1000
    )
    messages = []
    for _ in range(20):  # the consumer yields None until its fetch brings the messages
        message = next(consumer)
        if message is not None:
            messages.append(message)
        if len(messages) == 2:
            break
    assert [(m.actor_name, m.args[0]) for m in messages] == [
        (ACTOR, str(first.submission_id)),
        (ACTOR, str(second.submission_id)),
    ]
    assert JudgeJob.model_validate(messages[0].args[1]) == first.payload
    for message in messages:
        consumer.ack(message)
    consumer.close()
    redis.Redis.from_url(valkey_url).delete(position_key("judge.light"))


def test_an_unreachable_queue() -> None:
    async def scenario() -> int | None:
        queue = DramatiqQueue("redis://127.0.0.1:1/0")
        try:
            try:
                await queue.enqueue(job())
            except QueueUnavailableError:
                return await queue.position("judge.light", uuid.uuid4())
            raise AssertionError("the job was queued")
        finally:
            await queue.close()

    assert asyncio.run(scenario()) is None


def test_the_api_leaves_the_maintenance_to_the_workers(
    valkey_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The maintenance of the broker needs KEYS, which only the worker has
    (deploy/valkey/queue-users.acl.in): a sender never runs it, even when the dice say so."""
    # The broker rolls random.randint(1, MAINTENANCE_SCALE) against its chance: always 1 here.
    monkeypatch.setattr(random, "randint", lambda low, high: low)
    client = redis.Redis.from_url(valkey_url)
    # A dead worker: the maintenance would remove it.
    client.zadd("dramatiq:__heartbeats__", {"dead-worker": 0})

    async def scenario() -> None:
        queue = DramatiqQueue(valkey_url)
        try:
            await queue.enqueue(job("judge.rejudge"))
        finally:
            await queue.close()

    asyncio.run(scenario())
    assert client.zscore("dramatiq:__heartbeats__", "dead-worker") == 0
    client.delete(
        "dramatiq:__heartbeats__", "dramatiq:judge.rejudge", "dramatiq:judge.rejudge.msgs"
    )
    client.delete(position_key("judge.rejudge"))
