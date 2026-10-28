"""Artifacts of a submission for its author (specs/07 §4.4) and recreated FST (FR-WAV-05).

The list shows logs and events as they are stored and one FST per traced stage: the latest file, or
the latest recreation when it is newer — pending until the worker records it, failed when it did
not. What an FST covers comes from the metrics of its stage (`sim/v1`). Files are downloaded by a
presigned URL of the public storage endpoint; the testbench result file is never offered.

A recreation reruns the pipeline of the check up to the traced stage with the seed of the check: a
`judge_waveform` job with a fresh job token, keyed by its `waveforms` row. It spends the waveform
quota only when a job is queued: a ready or pending FST is answered as it is.
"""

import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import get_args

import anyio
import structlog
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.core.errors import ApiError, ErrorCode
from apparatica.core.ids import uuid7
from apparatica.core.storage import Storage
from apparatica.problems.models import Problem, ProblemVersion
from apparatica.submissions.models import Artifact, StageResult, ToolchainProfile
from apparatica.submissions.models import Submission as SubmissionRow
from apparatica.submissions.models import Waveform as WaveformRow
from apparatica.submissions.queue import QUEUE_UNAVAILABLE, JobQueue, QueueUnavailableError
from apparatica.submissions.quotas import Quotas
from apparatica.submissions.schemas import (
    ArtifactKind,
    ArtifactState,
    SubmissionArtifact,
    Waveform,
    WaveformRequest,
    WaveformSignal,
)
from apparatica.submissions.tokens import JobTokens
from judge.core.jobs import JudgeJob, TraceKey, WaveformJob, queue_name
from judge.core.verdict import SubmissionStatus

log = structlog.get_logger(__name__)

# Kinds a user may download; the testbench result file with the expected values of hidden tests
# is not one of them (specs/07 §4.4).
DOWNLOADABLE_ARTIFACT_KINDS: tuple[str, ...] = get_args(ArtifactKind)
FINAL_STATUSES = frozenset(get_args(SubmissionStatus))
# Saved as <submission>-<name>: the stored files of logs and events are compressed.
_FILE_NAMES = {"log": "{stage}.log.zst", "events": "events.jsonl.zst", "fst": "{stage}.fst"}


class _FailureMetrics(BaseModel):
    test: str
    cycle: int


class _TraceMetrics(BaseModel):
    """The trace fields of `sim/v1` (specs/04 §5); older results have no cursor time or signals."""

    model_config = ConfigDict(extra="ignore")

    trace: str
    trace_window: tuple[int, int]
    first_failure: _FailureMetrics
    trace_cursor_ps: int | None = None
    trace_signals: list[WaveformSignal] = []


def traced(stage: StageResult) -> _TraceMetrics | None:
    """The trace window a stage recorded, if any."""
    try:
        metrics = _TraceMetrics.model_validate(stage.metrics or {})
    except ValidationError:
        return None
    return metrics if metrics.trace == "recorded" else None


def waveform(stage: StageResult | None) -> Waveform | None:
    metrics = traced(stage) if stage is not None else None
    if metrics is None:
        return None
    return Waveform(
        test=metrics.first_failure.test,
        scope="failure_window",
        from_cycle=metrics.trace_window[0],
        to_cycle=metrics.trace_window[1],
        cursor_cycle=metrics.first_failure.cycle,
        cursor_time_ps=metrics.trace_cursor_ps,
        signals=metrics.trace_signals,
    )


def list_artifacts(
    artifacts: Sequence[Artifact],
    waveforms: Sequence[WaveformRow],
    stages: Iterable[StageResult],
    now: datetime,
) -> list[SubmissionArtifact]:
    """Logs and events in their order, then one FST per stage in the order of the stages."""
    by_key = {stage.stage_key: stage for stage in stages}
    items = [_item(a, None, now) for a in artifacts if a.kind != "fst"]
    files = {a.stage_key: a for a in artifacts if a.kind == "fst"}  # the latest wins
    jobs = {w.stage_key: w for w in waveforms if w.status != "ready"}
    for key in sorted(files.keys() | jobs.keys(), key=lambda k: _ordinal(by_key, k)):
        stage, file, job = by_key.get(key or ""), files.get(key), jobs.get(key or "")
        if job is not None and (file is None or job.created_at > file.created_at):
            state: ArtifactState = "pending" if job.status == "pending" else "failed"
            items.append(
                SubmissionArtifact(
                    kind="fst", stage=key, state=state, size_bytes=None, waveform=waveform(stage)
                )
            )
        elif file is not None:
            items.append(_item(file, stage, now))
    return items


def _ordinal(stages: dict[str, StageResult], key: str | None) -> int:
    stage = stages.get(key or "")
    return stage.ordinal if stage is not None else len(stages)


def _item(artifact: Artifact, stage: StageResult | None, now: datetime) -> SubmissionArtifact:
    expired = artifact.expires_at is not None and artifact.expires_at <= now
    return SubmissionArtifact(
        kind=artifact.kind,  # type: ignore[arg-type]  # filtered by the query
        stage=artifact.stage_key,
        state="expired" if expired else "ready",
        size_bytes=artifact.size_bytes,
        waveform=waveform(stage) if artifact.kind == "fst" else None,
    )


async def download_url(
    session: AsyncSession,
    storage: Storage,
    *,
    bucket: str,
    ttl_s: int,
    submission_id: uuid.UUID,
    kind: ArtifactKind,
    stage: str | None,
    guest_id: uuid.UUID | None,
) -> str:
    """A presigned URL of the latest file of this kind and stage that is still kept."""
    if guest_id is None:  # `== None` would match the submissions without an author
        raise ApiError(ErrorCode.NOT_FOUND, f"No submission {submission_id}")
    now = datetime.now(UTC)
    artifact = await session.scalar(
        select(Artifact)
        .join(SubmissionRow, SubmissionRow.id == Artifact.submission_id)
        .where(
            Artifact.submission_id == submission_id,
            SubmissionRow.guest_id == guest_id,
            Artifact.kind == kind,
            Artifact.stage_key.is_(None) if stage is None else Artifact.stage_key == stage,
            Artifact.purged_at.is_(None),
            (Artifact.expires_at.is_(None)) | (Artifact.expires_at > now),
        )
        .order_by(Artifact.created_at.desc())
        .limit(1)
    )
    if artifact is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"No {kind} artifact of {submission_id} to download")
    name = f"{submission_id}-" + _FILE_NAMES[kind].format(stage=stage)
    return await anyio.to_thread.run_sync(
        lambda: storage.download_url(bucket, artifact.storage_key, name, ttl_s)
    )


async def request_waveform(
    session: AsyncSession,
    submission_id: uuid.UUID,
    request: WaveformRequest,
    *,
    guest_id: uuid.UUID | None,
    tokens: JobTokens,
    queue: JobQueue,
    quotas: Quotas,
) -> SubmissionArtifact:
    """The FST of the failure window: as it is while kept or being recorded, else a new job."""
    if request.scope == "full_test":  # accounts arrive in phase 2
        raise ApiError(ErrorCode.UNAUTHENTICATED, "A whole test is recorded for signed-in users")
    # Locked: two requests at once queue one job.
    submission = (
        await session.scalar(
            select(SubmissionRow)
            .where(SubmissionRow.id == submission_id, SubmissionRow.guest_id == guest_id)
            .with_for_update()
        )
        if guest_id is not None
        else None
    )
    if submission is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"No submission {submission_id}")
    stages = list(
        await session.scalars(
            select(StageResult)
            .where(StageResult.submission_id == submission_id)
            .order_by(StageResult.ordinal)
        )
    )
    stage = next((s for s in stages if traced(s) is not None), None)
    if submission.status not in FINAL_STATUSES or stage is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"Submission {submission_id} has no trace window")
    artifacts = (
        await session.scalars(
            select(Artifact)
            .where(
                Artifact.submission_id == submission_id,
                Artifact.kind == "fst",
                Artifact.stage_key == stage.stage_key,
            )
            .order_by(Artifact.created_at)
        )
    ).all()
    waveforms = (
        await session.scalars(
            select(WaveformRow)
            .where(
                WaveformRow.submission_id == submission_id,
                WaveformRow.stage_key == stage.stage_key,
            )
            .order_by(WaveformRow.created_at)
        )
    ).all()
    for current in list_artifacts(artifacts, waveforms, [stage], datetime.now(UTC)):
        if current.state in ("ready", "pending"):
            return current

    assert guest_id is not None
    await quotas.admit_waveform(guest_id)
    row = WaveformRow(
        id=uuid7(), submission_id=submission_id, stage_key=stage.stage_key, status="pending"
    )
    session.add(row)
    job = await _job(session, submission, row.id, stage, stages, tokens)
    await session.commit()
    try:
        await queue.enqueue_waveform(queue_name(submission.queue_class), job)
    except QueueUnavailableError as error:
        row.status, row.error_code, row.finished_at = "failed", QUEUE_UNAVAILABLE, datetime.now(UTC)
        await session.commit()
        raise ApiError(ErrorCode.JUDGE_UNAVAILABLE, "The queue of checks is unavailable") from error
    log.info("waveform queued", submission_id=str(submission_id), waveform_id=str(row.id))
    return SubmissionArtifact(
        kind="fst",
        stage=stage.stage_key,
        state="pending",
        size_bytes=None,
        waveform=waveform(stage),
    )


async def _job(
    session: AsyncSession,
    submission: SubmissionRow,
    waveform_id: uuid.UUID,
    stage: StageResult,
    stages: Sequence[StageResult],
    tokens: JobTokens,
) -> WaveformJob:
    found = (
        await session.execute(
            select(ProblemVersion, Problem.slug, ToolchainProfile)
            .join(Problem, Problem.id == ProblemVersion.problem_id)
            .join(ToolchainProfile, ToolchainProfile.id == submission.toolchain_profile_id)
            .where(ProblemVersion.id == submission.problem_version_id)
        )
    ).one()
    version, slug, profile = found
    metrics = traced(stage)
    assert metrics is not None
    check = JudgeJob(
        submission_id=submission.id,
        token=tokens.issue(submission.id),
        problem=slug,
        version=version.version,
        package_uri=version.package_uri,
        content_hash=version.content_hash,
        resource_class=version.resource_class,
        kind="submit" if submission.kind == "submit" else "run",
        seed=submission.seed,
        code=submission.code,
        toolchain_profile=profile.id,
        toolchain_image=f"{profile.image}@{profile.image_digest}",
    )
    return WaveformJob(
        waveform_id=waveform_id,
        check=check,
        stage=stage.stage_key,
        stages=tuple(s.stage_key for s in stages if s.ordinal <= stage.ordinal),
        first_failure=TraceKey.model_validate(stage.metrics["first_failure"]),  # type: ignore[index]
    )
