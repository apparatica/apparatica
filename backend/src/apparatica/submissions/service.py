"""Creating and reading submissions (specs/07 §1).

A submission is checked against the current version of a published problem with the default
toolchain profile of its language and a fresh 63-bit seed: the triple makes a run reproducible
(specs/04 §1). Quotas, the guest cookie and the captcha arrive in phase 1 (T1.7).

The submission is committed before it is queued, so that a worker finds what it is given. A queue
that cannot be reached fails the submission with `internal_error`: it would otherwise wait forever.
"""

import secrets
import uuid
from datetime import UTC, datetime
from typing import get_args

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.core.errors import ApiError, ErrorCode
from apparatica.core.ids import uuid7
from apparatica.core.platform import SolutionLimits
from apparatica.problems.models import Problem, ProblemVersion
from apparatica.submissions.models import Artifact, StageResult, ToolchainProfile
from apparatica.submissions.models import Submission as SubmissionRow
from apparatica.submissions.queue import Job, JobQueue, QueueUnavailableError
from apparatica.submissions.schemas import (
    ArtifactKind,
    Submission,
    SubmissionArtifact,
    SubmissionCreate,
    SubmissionCreated,
    SubmissionStage,
)
from apparatica.submissions.tokens import JobTokens
from judge.core.jobs import JudgeJob, queue_name
from judge.core.stage import StageSummary
from judge.core.verdict import VerdictDetail

# Kinds a user may download; the testbench result file with the expected values of hidden tests
# is not one of them (specs/07 §4.4).
DOWNLOADABLE_ARTIFACT_KINDS: tuple[str, ...] = get_args(ArtifactKind)
QUEUE_UNAVAILABLE = "QUEUE_UNAVAILABLE"  # error code of a submission that was never queued


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

    submission = SubmissionRow(
        id=uuid7(),
        problem_version_id=version.id,
        kind=request.kind,
        code=request.code,
        seed=secrets.randbits(63),
        toolchain_profile_id=profile.id,
        queue_class=version.resource_class,
    )
    session.add(submission)
    await session.commit()
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
    result = await get_submission(session, submission.id, queue)
    assert result is not None
    return SubmissionCreated(**dict(result), quota=None)  # quotas arrive with guests (T1.7)


async def get_submission(
    session: AsyncSession, submission_id: uuid.UUID, queue: JobQueue
) -> Submission | None:
    row = await session.execute(
        select(SubmissionRow, ProblemVersion, Problem.slug)
        .join(ProblemVersion, ProblemVersion.id == SubmissionRow.problem_version_id)
        .join(Problem, Problem.id == ProblemVersion.problem_id)
        .where(SubmissionRow.id == submission_id)
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
