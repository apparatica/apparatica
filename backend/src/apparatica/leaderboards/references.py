"""Runs of reference solutions on the default toolchain profile (FR-SYN-04, T3.3).

The metrics of a reference solution are those of a Submit of its code on a profile: a run, a
submission without an author linked to the reference (`submissions.reference_solution_id`). The
leading ingestor queues the runs (`apparatica.judging.housekeeping.ReferenceRuns`): every
reference solution of the current version of a problem needs one on the default profile of its
language, so a run follows the import of a version, its publication and the switch of the default
profile. For the worker a run is a rejudge: it waits in `judge.rejudge` and takes no slot of live
users (specs/07 §3).

A run that ended with internal_error or was cancelled is repeated after `retry_after`; a run with a
verdict is final. A reference that is not accepted on a profile has no metrics there: the ingestor
logs it for review (specs/09 §2). Pages read the metrics of the latest accepted run
(`apparatica.leaderboards.boards.reference_metrics`).
"""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog
from sqlalchemy import and_, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.core.ids import uuid7
from apparatica.problems.models import Problem, ProblemVersion, ReferenceSolution
from apparatica.submissions.models import Submission, ToolchainProfile
from apparatica.submissions.queue import JobQueue, QueueUnavailableError
from apparatica.submissions.service import enqueue_check, judge_job
from apparatica.submissions.tokens import JobTokens

log = structlog.get_logger(__name__)

RETRIED = ("internal_error", "cancelled")  # no verdict on the reference: run it again


@dataclass(frozen=True)
class Unmeasured:
    """A reference solution that needs a run on the default profile of its language."""

    reference: ReferenceSolution
    slug: str
    version: ProblemVersion
    profile: ToolchainProfile


async def unmeasured(
    session: AsyncSession, now: datetime, retry_after: timedelta
) -> list[Unmeasured]:
    """Reference solutions of current versions without a run on the default profile, or whose
    latest run there ended without a verdict longer than `retry_after` ago."""
    latest = (
        select(Submission.status, Submission.finished_at)
        .where(
            Submission.reference_solution_id == ReferenceSolution.id,
            Submission.toolchain_profile_id == ToolchainProfile.id,
        )
        .order_by(Submission.created_at.desc())
        .limit(1)
        .lateral("latest")
    )
    rows = await session.execute(
        select(ReferenceSolution, Problem.slug, ProblemVersion, ToolchainProfile)
        .join(ProblemVersion, ProblemVersion.id == ReferenceSolution.problem_version_id)
        .join(Problem, Problem.current_version_id == ProblemVersion.id)
        .join(
            ToolchainProfile,
            and_(ToolchainProfile.language == ProblemVersion.language, ToolchainProfile.is_default),
        )
        .outerjoin(latest, true())
        .where(
            or_(
                latest.c.status.is_(None),
                and_(latest.c.status.in_(RETRIED), latest.c.finished_at < now - retry_after),
            )
        )
        .order_by(ReferenceSolution.id)
    )
    return [Unmeasured(*row) for row in rows]


async def queue_runs(
    session: AsyncSession,
    queue: JobQueue,
    tokens: JobTokens,
    now: datetime,
    retry_after: timedelta,
) -> int:
    """Queue the runs that `unmeasured` finds; returns how many. Each run is committed before its
    job is queued; a queue that cannot be reached ends the run with internal_error and stops the
    round."""
    queued = 0
    for item in await unmeasured(session, now, retry_after):
        run = Submission(
            id=uuid7(),
            problem_version_id=item.version.id,
            reference_solution_id=item.reference.id,
            kind="submit",
            code=item.reference.code,
            seed=secrets.randbits(63),
            toolchain_profile_id=item.profile.id,
            queue_class=item.version.resource_class,
        )
        session.add(run)
        await session.commit()
        job = judge_job(run, item.slug, item.version, item.profile, tokens)
        try:
            await enqueue_check(session, queue, run, job, rejudge=True)
        except QueueUnavailableError as error:
            log.warning("reference run not queued", submission_id=str(run.id), error=str(error))
            break
        log.info(
            "reference run queued",
            submission_id=str(run.id),
            problem=item.slug,
            version=item.version.version,
            reference=item.reference.title,
            toolchain_profile=item.profile.id,
        )
        queued += 1
    return queued
