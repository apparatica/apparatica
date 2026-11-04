"""Artifacts of a submission for its author (specs/07 §4.4) and recorded FST (FR-WAV-05).

The list shows logs and events as they are stored and up to two FST per traced stage, the failure
window and the whole failed test: for each the latest file, or the latest job when it is newer —
pending until the worker records it, failed when it did not. What an FST covers comes from the
metrics of its stage (`sim/v1`), the cycles of a whole test from its `waveforms` row. Files are
downloaded by a presigned URL of the public storage endpoint; the testbench result file is never
offered.

A job reruns the pipeline of the check up to the traced stage with the seed of the check: a
`judge_waveform` job with a fresh job token, keyed by its `waveforms` row. It records the expired
failure window again, or the whole failed test of a Run, for guests and users alike. It spends the
waveform quota only when a job is queued: a ready or pending FST is answered as it is.
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
from apparatica.submissions.quotas import Author, Quotas
from apparatica.submissions.schemas import (
    ArtifactKind,
    ArtifactState,
    SubmissionArtifact,
    Waveform,
    WaveformRequest,
    WaveformScope,
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
_FILE_NAMES = {"log": "{stage}.log.zst", "events": "events.jsonl.zst", "fst": "{stage}{scope}.fst"}
_SCOPE_SUFFIXES: dict[WaveformScope, str] = {"failure_window": "", "full_test": "-full"}


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


def waveform(stage: StageResult | None, row: WaveformRow | None = None) -> Waveform | None:
    """What the FST of a traced stage covers; `row` is the job that recorded it, if any. The
    cycles of a whole test are known once it is recorded."""
    metrics = traced(stage) if stage is not None else None
    if metrics is None:
        return None
    scope = scope_of(row)
    window = (
        (row.from_cycle, row.to_cycle) if row and scope == "full_test" else metrics.trace_window
    )
    return Waveform(
        test=metrics.first_failure.test,
        scope=scope,
        from_cycle=window[0],
        to_cycle=window[1],
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
    """Logs and events in their order, then the FST of each stage in the order of the stages,
    the failure window before the whole test. Both lists are in the order of creation."""
    by_key = {stage.stage_key: stage for stage in stages}
    items = [_item(a, None, None, now) for a in artifacts if a.kind != "fst"]
    recorded = {w.artifact_id: w for w in waveforms if w.artifact_id is not None}
    files: dict[tuple[str | None, WaveformScope], Artifact] = {}
    for fst in (a for a in artifacts if a.kind == "fst"):
        files[fst.stage_key, scope_of(recorded.get(fst.id))] = fst  # the latest wins
    jobs: dict[tuple[str | None, WaveformScope], WaveformRow] = {
        (w.stage_key, scope_of(w)): w for w in waveforms if w.status != "ready"
    }
    order = sorted(files.keys() | jobs.keys(), key=lambda k: (_ordinal(by_key, k[0]), k[1]))
    for key in order:
        stage, file, job = by_key.get(key[0] or ""), files.get(key), jobs.get(key)
        if job is not None and (file is None or job.created_at > file.created_at):
            failed = job.status != "pending"
            items.append(
                SubmissionArtifact(
                    kind="fst",
                    stage=key[0],
                    state="failed" if failed else "pending",
                    size_bytes=None,
                    error_code=job.error_code if failed else None,
                    waveform=waveform(stage, job),
                )
            )
        elif file is not None:
            items.append(_item(file, stage, recorded.get(file.id), now))
    return items


def scope_of(row: WaveformRow | None) -> WaveformScope:
    """What an FST covers: the window unless a job recorded the whole test."""
    return "full_test" if row is not None and row.scope == "full_test" else "failure_window"


def _ordinal(stages: dict[str, StageResult], key: str | None) -> int:
    stage = stages.get(key or "")
    return stage.ordinal if stage is not None else len(stages)


def _item(
    artifact: Artifact, stage: StageResult | None, row: WaveformRow | None, now: datetime
) -> SubmissionArtifact:
    expired = artifact.expires_at is not None and artifact.expires_at <= now
    state: ArtifactState = "expired" if expired else "ready"
    return SubmissionArtifact(
        kind=artifact.kind,  # type: ignore[arg-type]  # filtered by the query
        stage=artifact.stage_key,
        state=state,
        size_bytes=artifact.size_bytes,
        error_code=None,
        waveform=waveform(stage, row) if artifact.kind == "fst" else None,
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
    scope: WaveformScope,
    author: Author,
) -> str:
    """A presigned URL of the latest file of this kind and stage that is still kept; `scope`
    tells the FST of the failure window from that of the whole test."""
    now = datetime.now(UTC)
    whole = WaveformRow.scope == "full_test"
    artifact = await session.scalar(
        select(Artifact)
        .join(SubmissionRow, SubmissionRow.id == Artifact.submission_id)
        .outerjoin(WaveformRow, WaveformRow.artifact_id == Artifact.id)
        .where(
            Artifact.submission_id == submission_id,
            author.owns(),
            Artifact.kind == kind,
            Artifact.stage_key.is_(None) if stage is None else Artifact.stage_key == stage,
            Artifact.purged_at.is_(None),
            (Artifact.expires_at.is_(None)) | (Artifact.expires_at > now),
            whole if scope == "full_test" else WaveformRow.scope.is_(None) | ~whole,
        )
        .order_by(Artifact.created_at.desc())
        .limit(1)
    )
    if artifact is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"No {kind} artifact of {submission_id} to download")
    suffix = _SCOPE_SUFFIXES[scope] if kind == "fst" else ""
    name = f"{submission_id}-" + _FILE_NAMES[kind].format(stage=stage, scope=suffix)
    return await anyio.to_thread.run_sync(
        lambda: storage.download_url(bucket, artifact.storage_key, name, ttl_s)
    )


async def request_waveform(
    session: AsyncSession,
    submission_id: uuid.UUID,
    request: WaveformRequest,
    *,
    author: Author,
    tokens: JobTokens,
    queue: JobQueue,
    quotas: Quotas,
) -> SubmissionArtifact:
    """The FST of the failure window or of the whole failed test of a Run: as it is while kept
    or being recorded, else a new job."""
    scope = request.scope
    # Locked: two requests at once queue one job.
    submission = await session.scalar(
        select(SubmissionRow)
        .where(SubmissionRow.id == submission_id, author.owns())
        .with_for_update()
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
    if scope == "full_test" and submission.kind != "run":
        raise ApiError(ErrorCode.NOT_FOUND, "A whole test is traced only for a Run")
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
        assert current.waveform is not None
        if current.waveform.scope == scope and current.state in ("ready", "pending"):
            return current

    await quotas.admit_waveform(author)
    row = WaveformRow(
        id=uuid7(),
        submission_id=submission_id,
        stage_key=stage.stage_key,
        scope=scope,
        status="pending",
    )
    session.add(row)
    job = await _job(session, submission, row, stage, stages, tokens)
    await session.commit()
    try:
        await queue.enqueue_waveform(queue_name(submission.queue_class), job)
    except QueueUnavailableError as error:
        row.status, row.error_code, row.finished_at = "failed", QUEUE_UNAVAILABLE, datetime.now(UTC)
        await session.commit()
        raise ApiError(ErrorCode.JUDGE_UNAVAILABLE, "The queue of checks is unavailable") from error
    log.info(
        "waveform queued", submission_id=str(submission_id), waveform_id=str(row.id), scope=scope
    )
    return SubmissionArtifact(
        kind="fst",
        stage=stage.stage_key,
        state="pending",
        size_bytes=None,
        error_code=None,
        waveform=waveform(stage, row),
    )


async def _job(
    session: AsyncSession,
    submission: SubmissionRow,
    row: WaveformRow,
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
        waveform_id=row.id,
        check=check,
        stage=stage.stage_key,
        stages=tuple(s.stage_key for s in stages if s.ordinal <= stage.ordinal),
        first_failure=TraceKey.model_validate(stage.metrics["first_failure"]),  # type: ignore[index]
        scope=scope_of(row),
    )
