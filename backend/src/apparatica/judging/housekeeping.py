"""Periodic tasks of the leading ingestor (ADR-0009, specs/07 §3, §4.4).

- **Watchdog** — insurance only: a check `running` for longer than the limits of all its attempts
  plus a grace, with no lease held by a worker, ends with internal_error (`WATCHDOG_TIMEOUT`).
  It never requeues: the broker requeues the message of a dead worker.
- **Retention** — the files of expired artifacts are deleted from the `artifacts` bucket; the
  rows stay (`purged_at`), so a submission still lists an expired trace.
"""

import asyncio
import contextlib
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import redis.asyncio
import structlog
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import ValidationError
from sqlalchemy import func, select, update

from apparatica.core.db import Database
from apparatica.core.storage import Storage
from apparatica.judging.ingest import finalize, internal_error, transient
from apparatica.judging.leader import Leadership
from apparatica.judging.publish import publish_finalized
from apparatica.problems.models import ProblemVersion
from apparatica.submissions.events import FinalizedEvent
from apparatica.submissions.models import Artifact, Submission
from judge.core.jobs import ATTEMPT_MAX, lease_key
from judge.core.limits import ResourceClasses, check_timeout_s
from judge.core.package import Problem
from judge.core.stage import SubmissionKind

log = structlog.get_logger(__name__)

WATCHDOG_TIMEOUT = "WATCHDOG_TIMEOUT"
FALLBACK_CHECK_TIMEOUT_S = 3600.0  # the limits of a version that no longer parses
Clock = Callable[[], datetime]


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Watchdog:
    database: Database
    valkey: redis.asyncio.Redis
    classes: ResourceClasses
    grace_s: float
    clock: Clock = field(default=_now)

    async def __call__(self) -> int:
        """Ends the stuck checks; returns how many."""
        async with self.database.sessions() as session:
            rows = (
                await session.execute(
                    select(
                        Submission.id,
                        Submission.kind,
                        func.coalesce(Submission.started_at, Submission.created_at),
                        ProblemVersion,
                    )
                    .join(ProblemVersion, ProblemVersion.id == Submission.problem_version_id)
                    .where(Submission.status == "running")
                )
            ).all()
        now, stuck = self.clock(), 0
        for submission_id, kind, started_at, version in rows:
            deadline = started_at + timedelta(seconds=self._limit_s(version, kind))
            if now < deadline or await self.valkey.exists(lease_key(submission_id)):
                continue
            event = await self._fail(submission_id, now)
            if event is not None:
                stuck += 1
                log.warning("stuck check ended", submission_id=str(submission_id))
                await publish_finalized(self.valkey, submission_id, event)
        return stuck

    def _limit_s(self, version: ProblemVersion, kind: str) -> float:
        """Every attempt may run its whole limit; the grace covers the requeue between them."""
        try:
            problem = Problem.model_validate(version.manifest)
            submission_kind: SubmissionKind = "submit" if kind == "submit" else "run"
            attempt = check_timeout_s(problem, submission_kind, self.classes)
        except (ValidationError, ValueError, KeyError) as error:
            log.error("limits of a version unknown", version=str(version.id), error=str(error))
            attempt = FALLBACK_CHECK_TIMEOUT_S
        return ATTEMPT_MAX * attempt + self.grace_s

    async def _fail(self, submission_id: uuid.UUID, now: datetime) -> FinalizedEvent | None:
        async with self.database.sessions.begin() as session:
            submission = await session.get(Submission, submission_id, with_for_update=True)
            if submission is None or submission.status != "running":  # the ingestor was faster
                return None
            return finalize(submission, internal_error(WATCHDOG_TIMEOUT), now)


@dataclass
class ArtifactPurge:
    database: Database
    storage: Storage
    bucket: str
    batch: int = 500
    clock: Clock = field(default=_now)

    async def __call__(self) -> int:
        """Deletes the files of expired artifacts, a batch at a time; returns how many."""
        now = self.clock()
        async with self.database.sessions() as session:
            rows = (
                await session.execute(
                    select(Artifact.id, Artifact.storage_key)
                    .where(
                        Artifact.expires_at.is_not(None),
                        Artifact.purged_at.is_(None),
                        Artifact.expires_at <= now,
                    )
                    .order_by(Artifact.expires_at)
                    .limit(self.batch)
                )
            ).all()
        purged = []
        for artifact_id, key in rows:
            try:
                await asyncio.to_thread(self.storage.delete, self.bucket, key)
            except (BotoCoreError, ClientError) as error:  # the next run tries again
                log.warning("expired artifact not deleted", key=key, error=str(error))
                continue
            purged.append(artifact_id)
        if purged:
            async with self.database.sessions.begin() as session:
                await session.execute(
                    update(Artifact).where(Artifact.id.in_(purged)).values(purged_at=now)
                )
            log.info("expired artifacts deleted", count=len(purged))
        return len(purged)


@dataclass
class Periodic:
    name: str
    every_s: float
    run: Callable[[], Awaitable[int]]
    due: float = 0.0  # time.monotonic() of the next run


class Housekeeping:
    """Runs the periodic tasks while this instance leads; a failed task is retried next time."""

    def __init__(
        self, leadership: Leadership, tasks: Sequence[Periodic], *, tick_s: float = 10
    ) -> None:
        self._leadership = leadership
        self._tasks = tasks
        self._tick_s = tick_s

    async def tick(self) -> bool:
        """One round; whether this instance leads."""
        if not await self._leadership.hold():
            return False
        for task in self._tasks:
            if time.monotonic() < task.due:
                continue
            task.due = time.monotonic() + task.every_s
            try:
                await task.run()
            except Exception as error:
                if transient(error):
                    log.warning("periodic task failed", task=task.name, error=str(error))
                else:  # a bug must not stop the ingest of results
                    log.exception("periodic task failed", task=task.name)
        return True

    async def run(self, stop: asyncio.Event) -> None:
        try:
            while not stop.is_set():
                try:
                    await self.tick()
                except Exception as error:
                    if not transient(error):
                        raise
                    log.warning("leadership unknown", error=str(error))
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), self._tick_s)
        finally:
            with contextlib.suppress(Exception):
                await self._leadership.release()
