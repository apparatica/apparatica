"""Periodic tasks of the leading ingestor (ADR-0009, specs/07 §3, §4.4).

- **Watchdog** — insurance only: a check `running` for longer than the limits of all its attempts
  plus a grace, with no lease held by a worker, ends with internal_error (`WATCHDOG_TIMEOUT`).
  It never requeues: the broker requeues the message of a dead worker. A recreated FST pending as
  long since it was requested fails the same way (FR-WAV-05).
- **Retention** — the files of expired artifacts are deleted from the `artifacts` bucket; the
  rows stay (`purged_at`), so a submission still lists an expired trace.
- **Guests** — finished guest submissions older than `guest_submissions_days` are deleted with
  their rows and the files of their artifacts (decision ОВ-13).
- **Addresses** — the salted hashes of client addresses older than `client_ip_hash_days` are
  cleared (NFR-PRIV-01).
- **Problem stats** — the authors of every problem with a judged and with an accepted Submit, for
  the acceptance rate of the catalogue (FR-CAT-04).
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
from sqlalchemy import CursorResult, and_, delete, distinct, func, literal, select, update
from sqlalchemy.dialects.postgresql import insert

from apparatica.core.db import Database
from apparatica.core.storage import Storage
from apparatica.judging.ingest import finalize, internal_error, transient
from apparatica.judging.leader import Leadership
from apparatica.judging.publish import publish_finalized
from apparatica.problems.models import Problem as ProblemRow
from apparatica.problems.models import ProblemStats, ProblemVersion
from apparatica.submissions.events import FinalizedEvent
from apparatica.submissions.models import Artifact, Submission, Waveform
from judge.core.jobs import ATTEMPT_MAX, lease_key
from judge.core.limits import ResourceClasses, check_timeout_s
from judge.core.package import Problem
from judge.core.stage import SubmissionKind

log = structlog.get_logger(__name__)

WATCHDOG_TIMEOUT = "WATCHDOG_TIMEOUT"
ACCEPTED = ("accepted", "accepted_with_warnings")
UNJUDGED = ("queued", "running", "cancelled", "internal_error")  # no verdict on the solution
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
        """Ends the stuck checks and waveform jobs; returns how many."""
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
        return stuck + await self._waveforms(now)

    async def _waveforms(self, now: datetime) -> int:
        """The queue wait counts too: a waveform job has no running state."""
        async with self.database.sessions() as session:
            rows = (
                await session.execute(
                    select(Waveform.id, Waveform.created_at, Submission.kind, ProblemVersion)
                    .join(Submission, Submission.id == Waveform.submission_id)
                    .join(ProblemVersion, ProblemVersion.id == Submission.problem_version_id)
                    .where(Waveform.status == "pending")
                )
            ).all()
        stuck = []
        for waveform_id, created_at, kind, version in rows:
            deadline = created_at + timedelta(seconds=self._limit_s(version, kind))
            if now >= deadline and not await self.valkey.exists(lease_key(waveform_id)):
                stuck.append(waveform_id)
        if not stuck:
            return 0
        async with self.database.sessions.begin() as session:
            result = await session.execute(
                update(Waveform)
                .where(Waveform.id.in_(stuck), Waveform.status == "pending")
                .values(status="failed", error_code=WATCHDOG_TIMEOUT, finished_at=now)
            )
        failed = result.rowcount if isinstance(result, CursorResult) else 0
        log.warning("stuck waveforms failed", count=failed)
        return failed

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
class GuestPurge:
    database: Database
    storage: Storage
    bucket: str
    days: int
    batch: int = 200
    clock: Clock = field(default=_now)

    async def __call__(self) -> int:
        """Deletes a batch of old guest submissions; returns how many. A submission whose file
        cannot be deleted stays until the next run."""
        cutoff = self.clock() - timedelta(days=self.days)
        async with self.database.sessions() as session:
            ids = list(
                await session.scalars(
                    select(Submission.id)
                    .where(
                        Submission.guest_id.is_not(None),  # phase 2: and no user
                        Submission.created_at < cutoff,
                        Submission.status.not_in(("queued", "running")),  # the ingestor's
                    )
                    .order_by(Submission.created_at)
                    .limit(self.batch)
                )
            )
            files = (
                await session.execute(
                    select(Artifact.submission_id, Artifact.storage_key).where(
                        Artifact.submission_id.in_(ids), Artifact.purged_at.is_(None)
                    )
                )
            ).all()
        kept: set[uuid.UUID] = set()
        for submission_id, key in files:
            if submission_id in kept:
                continue
            try:
                await asyncio.to_thread(self.storage.delete, self.bucket, key)
            except (BotoCoreError, ClientError) as error:  # the next run tries again
                log.warning("guest artifact not deleted", key=key, error=str(error))
                kept.add(submission_id)
        deleted = [submission_id for submission_id in ids if submission_id not in kept]
        if deleted:
            async with self.database.sessions.begin() as session:  # stages, artifacts: cascade
                await session.execute(delete(Submission).where(Submission.id.in_(deleted)))
            log.info("guest submissions deleted", count=len(deleted))
        return len(deleted)


@dataclass
class AddressPurge:
    database: Database
    days: int
    clock: Clock = field(default=_now)

    async def __call__(self) -> int:
        """Clears the old hashes of client addresses; returns how many."""
        cutoff = self.clock() - timedelta(days=self.days)
        async with self.database.sessions.begin() as session:
            result = await session.execute(
                update(Submission)
                .where(Submission.client_ip_hash.is_not(None), Submission.created_at < cutoff)
                .values(client_ip_hash=None)
            )
        cleared = result.rowcount if isinstance(result, CursorResult) else 0
        if cleared:
            log.info("address hashes cleared", count=cleared)
        return cleared


@dataclass
class ProblemStatsRefresh:
    database: Database
    clock: Clock = field(default=_now)

    async def __call__(self) -> int:
        """Counts the authors of every problem, over all its versions; returns how many problems.
        Guest submissions count while they are kept (`guest_submissions_days`)."""
        author = Submission.guest_id  # phase 2: the user, or the guest
        counts = (
            select(
                ProblemRow.id,
                func.count(distinct(author)),
                func.count(distinct(author)).filter(Submission.status.in_(ACCEPTED)),
                literal(self.clock()),
            )
            .select_from(ProblemRow)
            .outerjoin(ProblemVersion, ProblemVersion.problem_id == ProblemRow.id)
            .outerjoin(
                Submission,
                and_(
                    Submission.problem_version_id == ProblemVersion.id,
                    Submission.kind == "submit",
                    Submission.status.not_in(UNJUDGED),
                ),
            )
            .group_by(ProblemRow.id)
        )
        columns = ["problem_id", "authors", "accepted_authors", "updated_at"]
        statement = insert(ProblemStats).from_select(columns, counts)
        statement = statement.on_conflict_do_update(
            index_elements=[ProblemStats.problem_id],
            set_={name: statement.excluded[name] for name in columns[1:]},
        )
        async with self.database.sessions.begin() as session:
            result = await session.execute(statement)
        return result.rowcount if isinstance(result, CursorResult) else 0


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
