"""Handing checks to the workers (ADR-0002). The Dramatiq queue arrives in T1.1; until then a
submission stays `queued`."""

import uuid
from dataclasses import dataclass
from typing import Protocol

import structlog

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class Job:
    submission_id: uuid.UUID
    queue: str  # judge.<resource class>
    token: str  # the job token (apparatica.submissions.tokens)


class JobQueue(Protocol):
    async def enqueue(self, job: Job) -> None: ...


class NoQueue:
    """Phase 0: there are no workers yet, the job is only logged."""

    async def enqueue(self, job: Job) -> None:
        log.info("no job queue yet", submission_id=str(job.submission_id), queue=job.queue)
