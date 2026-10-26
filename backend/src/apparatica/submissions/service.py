"""Creating and reading submissions (specs/07 §1).

A submission is checked against the current version of a published problem with the default
toolchain profile of its language and a fresh 63-bit seed: the triple makes a run reproducible
(specs/04 §1). A submission belongs to its author, a guest until accounts arrive (phase 2): other
callers get NOT_FOUND, as if it did not exist. Before it is stored come the quotas of the author
(`quotas`), the captcha (`apparatica.captcha.service`), then the checks of the address.

The submission is committed before it is queued, so that a worker finds what it is given. A queue
that cannot be reached fails the submission with `internal_error`: it would otherwise wait forever.
"""

import base64
import secrets
import uuid
from datetime import UTC, datetime
from typing import get_args

import structlog
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.captcha.service import Captcha
from apparatica.core.errors import ApiError, ErrorCode
from apparatica.core.ids import uuid7
from apparatica.core.platform import SolutionLimits
from apparatica.problems.models import Problem, ProblemVersion
from apparatica.submissions.live import Watched
from apparatica.submissions.models import Artifact, StageResult, ToolchainProfile
from apparatica.submissions.models import Submission as SubmissionRow
from apparatica.submissions.queue import Job, JobQueue, QueueUnavailableError
from apparatica.submissions.quotas import Author, Quotas
from apparatica.submissions.schemas import (
    ArtifactKind,
    Submission,
    SubmissionArtifact,
    SubmissionCreate,
    SubmissionCreated,
    SubmissionStage,
    SubmissionSummary,
)
from apparatica.submissions.tokens import JobTokens
from judge.core.jobs import JudgeJob, queue_name
from judge.core.stage import StageSummary
from judge.core.verdict import SubmissionStatus, VerdictDetail

log = structlog.get_logger(__name__)

# Kinds a user may download; the testbench result file with the expected values of hidden tests
# is not one of them (specs/07 §4.4).
DOWNLOADABLE_ARTIFACT_KINDS: tuple[str, ...] = get_args(ArtifactKind)
QUEUE_UNAVAILABLE = "QUEUE_UNAVAILABLE"  # error code of a submission that was never queued
FINAL_STATUSES = frozenset(get_args(SubmissionStatus))


def check_size(code: str, limits: SolutionLimits) -> None:
    size = len(code.encode("utf-8"))
    lines = code.count("\n") + (0 if code.endswith("\n") else 1)
    if size > limits.max_bytes or lines > limits.max_lines:
        raise ApiError(
            ErrorCode.CODE_TOO_LARGE,
            f"The solution has {size} bytes and {lines} lines;"
            f" the limits are {limits.max_bytes} bytes and {limits.max_lines} lines",
            params={
                "max_bytes": limits.max_bytes,
                "max_lines": limits.max_lines,
                "bytes": size,
                "lines": lines,
            },
        )


async def create_submission(
    session: AsyncSession,
    request: SubmissionCreate,
    *,
    limits: SolutionLimits,
    tokens: JobTokens,
    queue: JobQueue,
    quotas: Quotas,
    captcha: Captcha,
    author: Author,
) -> SubmissionCreated:
    check_size(request.code, limits)
    row = await session.execute(
        select(Problem.slug, ProblemVersion)
        .join(ProblemVersion, ProblemVersion.id == Problem.current_version_id)
        .where(Problem.slug == request.problem, Problem.is_published)
    )
    found = row.one_or_none()
    if found is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"No published problem {request.problem!r}")
    _, version = found
    if request.version != version.version:
        # Rejudge of older versions goes through the rejudge queue (phase 5), not this endpoint.
        raise ApiError(
            ErrorCode.PROBLEM_VERSION_OUTDATED,
            f"Version {request.version} is not the current version {version.version}",
            params={"current_version": version.version},
        )
    profile = await session.scalar(
        select(ToolchainProfile).where(
            ToolchainProfile.language == version.language, ToolchainProfile.is_default
        )
    )
    if profile is None:
        raise ApiError(
            ErrorCode.JUDGE_UNAVAILABLE,
            f"No default toolchain profile for {version.language!r}",
        )
    await quotas.admit(
        session,
        author,
        kind=request.kind,
        problem_id=version.problem_id,
        resource_class=version.resource_class,
    )
    await captcha.check(author.guest_id, author.address, request.captcha)
    await quotas.admit_address(author)

    submission = SubmissionRow(
        id=uuid7(),
        problem_version_id=version.id,
        kind=request.kind,
        code=request.code,
        seed=secrets.randbits(63),
        toolchain_profile_id=profile.id,
        queue_class=version.resource_class,
        guest_id=author.guest_id,
        client_ip_hash=author.address,
    )
    session.add(submission)
    await session.commit()
    await captcha.count(author.guest_id, author.address)
    job = JudgeJob(
        submission_id=submission.id,
        token=tokens.issue(submission.id),
        problem=request.problem,
        version=version.version,
        package_uri=version.package_uri,
        content_hash=version.content_hash,
        resource_class=version.resource_class,
        kind=request.kind,
        seed=submission.seed,
        code=submission.code,
        toolchain_profile=profile.id,
        toolchain_image=f"{profile.image}@{profile.image_digest}",
    )
    try:
        await queue.enqueue(Job(queue=queue_name(version.resource_class), payload=job))
    except QueueUnavailableError as error:
        submission.status = "internal_error"
        submission.verdict_detail = VerdictDetail(error_codes=[QUEUE_UNAVAILABLE]).model_dump(
            mode="json"
        )
        submission.finished_at = datetime.now(UTC)
        await session.commit()
        raise ApiError(ErrorCode.JUDGE_UNAVAILABLE, "The queue of checks is unavailable") from error
    if submission.kind == "run":
        await preempt_runs(session, submission, version.problem_id, queue)
    result = await get_submission(session, submission.id, queue, author.guest_id)
    assert result is not None
    return SubmissionCreated(**dict(result), quota=await quotas.status(session, author.guest_id))


async def preempt_runs(
    session: AsyncSession, submission: SubmissionRow, problem_id: uuid.UUID, queue: JobQueue
) -> None:
    """A new Run cancels the unfinished Runs of the same problem by the same author (FR-JDG-10).
    The author is a guest until accounts arrive (phase 2)."""
    previous = await session.scalars(
        select(SubmissionRow.id)
        .join(ProblemVersion, ProblemVersion.id == SubmissionRow.problem_version_id)
        .where(
            ProblemVersion.problem_id == problem_id,
            SubmissionRow.guest_id == submission.guest_id,
            SubmissionRow.kind == "run",
            SubmissionRow.status.in_(("queued", "running")),
            SubmissionRow.id != submission.id,
        )
    )
    for submission_id in previous:
        try:
            await queue.cancel(submission_id, "preempted")
        except QueueUnavailableError as error:  # the new run counts more than the old one
            log.warning("run not preempted", submission_id=str(submission_id), error=str(error))


async def cancel_submission(
    session: AsyncSession, submission_id: uuid.UUID, queue: JobQueue, guest_id: uuid.UUID | None
) -> None:
    """Ask for the cancellation; the status changes when the ingestor stores it (`finalized`)."""
    status = (
        await session.scalar(
            select(SubmissionRow.status).where(
                SubmissionRow.id == submission_id, SubmissionRow.guest_id == guest_id
            )
        )
        if guest_id is not None  # `== None` would match the submissions without an author
        else None
    )
    if status is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"No submission {submission_id}")
    if status in FINAL_STATUSES:
        raise ApiError(ErrorCode.SUBMISSION_FINISHED, f"Submission {submission_id} is {status}")
    try:
        await queue.cancel(submission_id, "user")
    except QueueUnavailableError as error:
        raise ApiError(ErrorCode.JUDGE_UNAVAILABLE, "The queue of checks is unavailable") from error


async def get_submission(
    session: AsyncSession, submission_id: uuid.UUID, queue: JobQueue, guest_id: uuid.UUID | None
) -> Submission | None:
    """The submission if `guest_id` is its author."""
    if guest_id is None:  # `== None` would match the submissions without an author
        return None
    row = await session.execute(
        select(SubmissionRow, ProblemVersion, Problem.slug)
        .join(ProblemVersion, ProblemVersion.id == SubmissionRow.problem_version_id)
        .join(Problem, Problem.id == ProblemVersion.problem_id)
        .where(SubmissionRow.id == submission_id, SubmissionRow.guest_id == guest_id)
    )
    found = row.one_or_none()
    if found is None:
        return None
    submission, version, slug = found
    stages = await session.scalars(
        select(StageResult)
        .where(StageResult.submission_id == submission_id)
        .order_by(StageResult.ordinal)
    )
    artifacts = await session.scalars(
        select(Artifact)
        .where(
            Artifact.submission_id == submission_id,
            Artifact.kind.in_(DOWNLOADABLE_ARTIFACT_KINDS),
        )
        .order_by(Artifact.created_at, Artifact.kind)
    )
    now = datetime.now(UTC)
    return Submission(
        id=submission.id,
        problem=slug,
        problem_title=version.title,
        version=version.version,
        kind=submission.kind,  # type: ignore[arg-type]  # checked by the table constraint
        status=submission.status,  # type: ignore[arg-type]  # a submission_status value
        code=submission.code,
        seed=str(submission.seed),
        toolchain_profile=submission.toolchain_profile_id,
        queue_position=(
            await queue.position(queue_name(submission.queue_class), submission.id)
            if submission.status == "queued"
            else None
        ),
        eta_s=None,  # needs the median check time of the ingestor (specs/07 §3)
        created_at=submission.created_at,
        started_at=submission.started_at,
        finished_at=submission.finished_at,
        verdict_detail=(
            VerdictDetail.model_validate(submission.verdict_detail)
            if submission.verdict_detail is not None
            else None
        ),
        stages=[
            SubmissionStage(
                key=stage.stage_key,
                type=stage.stage_type,
                ordinal=stage.ordinal,
                status=stage.status,  # type: ignore[arg-type]  # a stage_status value
                failure_kind=stage.failure_kind,  # type: ignore[arg-type]  # table constraint
                error_code=stage.error_code,
                started_at=stage.started_at,
                finished_at=stage.finished_at,
                duration_ms=stage.duration_ms,
                metrics_schema=stage.metrics_schema,
                metrics=stage.metrics or {},
                summary=StageSummary.model_validate(stage.summary or {}),
            )
            for stage in stages
        ],
        artifacts=[
            SubmissionArtifact(
                kind=artifact.kind,  # type: ignore[arg-type]  # filtered by the query
                stage=artifact.stage_key,
                state="expired"
                if artifact.expires_at is not None and artifact.expires_at <= now
                else "ready",
                size_bytes=artifact.size_bytes,
                waveform=None,  # trace windows are stored with the worker artifacts (T1.2b)
            )
            for artifact in artifacts
        ],
    )


async def watch_submission(
    session: AsyncSession, submission_id: uuid.UUID, guest_id: uuid.UUID | None
) -> Watched | None:
    """What the event stream of a submission needs (specs/07 §4.2), for its author."""
    submission = await session.get(SubmissionRow, submission_id)
    if submission is None or guest_id is None or submission.guest_id != guest_id:
        return None
    journal = await session.scalar(
        select(Artifact.storage_key)
        .where(
            Artifact.submission_id == submission_id,
            Artifact.kind == "events",
            Artifact.purged_at.is_(None),
        )
        .order_by(Artifact.created_at.desc(), Artifact.storage_key.desc())
        .limit(1)
    )
    return Watched(
        id=submission.id,
        status=submission.status,
        final=submission.status in FINAL_STATUSES,
        queue=queue_name(submission.queue_class),
        verdict_detail=submission.verdict_detail,
        finished_at=submission.finished_at,
        journal=journal,
    )


async def list_submissions(
    session: AsyncSession,
    guest_id: uuid.UUID | None,
    *,
    problem: str | None,
    cursor: str | None,
    limit: int,
) -> tuple[list[SubmissionSummary], str | None]:
    """A page of the submissions of a guest, newest first, and the cursor of the next page."""
    after = _decode_cursor(cursor) if cursor is not None else None
    if guest_id is None:
        return [], None
    query = (
        select(SubmissionRow, ProblemVersion, Problem.slug)
        .join(ProblemVersion, ProblemVersion.id == SubmissionRow.problem_version_id)
        .join(Problem, Problem.id == ProblemVersion.problem_id)
        .where(SubmissionRow.guest_id == guest_id)
        .order_by(SubmissionRow.created_at.desc(), SubmissionRow.id.desc())
        .limit(limit + 1)
    )
    if problem is not None:
        query = query.where(Problem.slug == problem)
    if after is not None:
        query = query.where(tuple_(SubmissionRow.created_at, SubmissionRow.id) < after)
    rows = (await session.execute(query)).all()
    items = [
        SubmissionSummary(
            id=submission.id,
            problem=slug,
            problem_title=version.title,
            version=version.version,
            kind=submission.kind,  # type: ignore[arg-type]  # checked by the table constraint
            status=submission.status,  # type: ignore[arg-type]  # a submission_status value
            verdict_detail=(
                VerdictDetail.model_validate(submission.verdict_detail)
                if submission.verdict_detail is not None
                else None
            ),
            created_at=submission.created_at,
            finished_at=submission.finished_at,
        )
        for submission, version, slug in rows[:limit]
    ]
    if len(rows) <= limit:
        return items, None
    last = rows[limit - 1][0]
    return items, _encode_cursor(last.created_at, last.id)


def _encode_cursor(created_at: datetime, submission_id: uuid.UUID) -> str:
    text = f"{created_at.isoformat()}|{submission_id}"
    return base64.urlsafe_b64encode(text.encode()).rstrip(b"=").decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """The position of the last item of the previous page; VALIDATION_ERROR if malformed."""
    try:
        text = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        created_at, submission_id = text.split("|")
        after = datetime.fromisoformat(created_at), uuid.UUID(submission_id)
    except ValueError:  # bad base64, UTF-8, separator, time or id
        after = None
    if after is None or after[0].tzinfo is None:
        raise RequestValidationError(
            [{"loc": ("query", "cursor"), "msg": "Invalid cursor", "type": "value_error"}]
        )
    return after
