"""Handing checks to the workers (ADR-0002, specs/07 §3).

A job is a Dramatiq message for the `judge_submission` actor on `valkey-queue`; the API sends it
without the worker code (`judge.core.jobs` is the contract). The sorted set `queue:<queue>` keeps
the waiting submissions by the time they were queued: the API adds a submission, the worker that
takes it removes it, and the rank is the position in the queue.
"""

import contextlib
import time
import uuid
from dataclasses import dataclass
from typing import Protocol

import anyio
import redis.asyncio
import structlog
from dramatiq import Message
from dramatiq.brokers.redis import RedisBroker
from dramatiq.errors import BrokerError

from judge.core.jobs import (
    ACTOR,
    CANCEL_CHANNEL,
    CANCEL_TTL_S,
    QUEUES,
    CancelReason,
    JudgeJob,
    cancel_key,
    position_key,
)

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class Job:
    queue: str  # judge.<resource class> or judge.rejudge
    payload: JudgeJob

    @property
    def submission_id(self) -> uuid.UUID:
        return self.payload.submission_id


class QueueUnavailableError(Exception):
    """The job was not queued: the broker cannot be reached."""


class JobQueue(Protocol):
    async def enqueue(self, job: Job) -> None:
        """Raises QueueUnavailableError."""
        ...

    async def position(self, queue: str, submission_id: uuid.UUID) -> int | None:
        """1 for the next submission to be taken; None when it is not waiting."""
        ...

    async def cancel(self, submission_id: uuid.UUID, reason: CancelReason) -> None:
        """Ask the worker that runs the check, or the ingestor, to cancel it (specs/07 §3).
        Raises QueueUnavailableError."""
        ...

    async def close(self) -> None: ...


class NoQueue:
    """No queue configured (development without workers): the job is only logged."""

    async def enqueue(self, job: Job) -> None:
        log.info("no job queue", submission_id=str(job.submission_id), queue=job.queue)

    async def position(self, queue: str, submission_id: uuid.UUID) -> int | None:
        return None

    async def cancel(self, submission_id: uuid.UUID, reason: CancelReason) -> None:
        raise QueueUnavailableError("no queue: no worker or ingestor can cancel")

    async def close(self) -> None:
        pass


class DramatiqQueue:
    def __init__(self, url: str) -> None:
        self._broker = RedisBroker(url=url, middleware=[])  # it only sends
        for queue in QUEUES:
            self._broker.declare_queue(queue)
        self._redis = redis.asyncio.Redis.from_url(url)

    async def enqueue(self, job: Job) -> None:
        key, member = position_key(job.queue), str(job.submission_id)
        message: Message[None] = Message(
            queue_name=job.queue,
            actor_name=ACTOR,
            args=(member, job.payload.model_dump(mode="json")),
            kwargs={},
            options={},
        )
        try:
            # Before the message: the worker that takes it removes the position.
            await self._redis.zadd(key, {member: time.time()})
            # Dramatiq is synchronous; the call is short (ADR-0002).
            await anyio.to_thread.run_sync(self._broker.enqueue, message)
        except (redis.RedisError, BrokerError) as error:
            await self._forget(key, member)
            raise QueueUnavailableError(str(error)) from error

    async def _forget(self, key: str, member: str) -> None:
        # The broker is down: a stale position does no harm, the submission has failed.
        with contextlib.suppress(redis.RedisError):
            await self._redis.zrem(key, member)

    async def position(self, queue: str, submission_id: uuid.UUID) -> int | None:
        try:
            rank = await self._redis.zrank(position_key(queue), str(submission_id))
        except redis.RedisError as error:  # a submission is still worth showing without it
            log.warning("queue position unavailable", error=repr(error))
            return None
        return rank + 1 if isinstance(rank, int) else None

    async def cancel(self, submission_id: uuid.UUID, reason: CancelReason) -> None:
        """The key first: a worker that starts the attempt later finds it; the message reaches
        the worker that runs it and the ingestor, which ends a check still waiting."""
        try:
            async with self._redis.pipeline(transaction=False) as pipe:
                pipe.set(cancel_key(submission_id), reason, ex=CANCEL_TTL_S)
                pipe.publish(CANCEL_CHANNEL, f"{submission_id} {reason}")
                await pipe.execute()
        except redis.RedisError as error:
            raise QueueUnavailableError(str(error)) from error

    async def close(self) -> None:
        await self._redis.aclose()
        self._broker.close()
