"""Pipeline execution: the stages of `pipelines.practice.<kind>` in order (specs/07 §2.7).

A stage after a failed one or after a platform error is skipped; cancellation marks the running
stage cancelled and skips the rest. The pipeline reports stage results; the verdict is aggregated
separately (`judge.core.verdict`) by whoever owns the final status.

A deterministic plan (`StagePlan.cache`, e.g. synthesis) is looked up in the stage cache first and
replayed from there; its fresh run is kept once the stage ends with a result the same code always
gets (FR-JDG-11).
"""

import base64
import binascii
import threading
import time
import traceback
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from judge.core.cache import NO_CACHE, BuildCache, plan_key
from judge.core.events import (
    DoneEvent,
    EventSink,
    LogEvent,
    StageEndEvent,
    StageStartEvent,
    TestEvent,
    TruncatedEvent,
)
from judge.core.executor import Executor, ExecutorError, OnLine
from judge.core.limits import ResourceClasses, stage_limits
from judge.core.package import Problem
from judge.core.registry import LanguageModule
from judge.core.stage import (
    Channel,
    CommandResult,
    ExecResult,
    FinishedStage,
    SkipReason,
    Stage,
    StageContext,
    StageOutcome,
    StagePlan,
    StageResult,
    StageSummary,
    SubmissionKind,
    TraceScope,
)

# Runs per stage: the first one plus follow-ups such as the trace window of `sim`.
MAX_RUNS_PER_STAGE = 4
# A replayed run of a deterministic plan says so before its console output.
CACHED_RUN_NOTE = "result from the cache: this code was checked earlier on this toolchain"
# A larger run (netlists, reports) is not kept in the stage cache.
CACHED_RUN_LIMIT = 32 << 20

# Receives the artifacts of a finished stage: (stage key, file name, content).
ArtifactSink = Callable[[str, str, bytes], None]


class PipelineConfigError(ValueError):
    """The problem's pipeline cannot run: unknown stage type or invalid stage config."""


@dataclass(frozen=True)
class Job:
    problem: Problem
    package_dir: Path
    kind: SubmissionKind
    seed: int
    solution: bytes
    # Stage keys to run instead of pipelines.practice.<kind>, e.g. only the checks of a template.
    stages: tuple[str, ...] | None = None
    # A whole failed test is traced on request (FR-WAV-05), not only the window of the mismatch.
    trace: TraceScope = "failure_window"


@dataclass(frozen=True)
class _Planned:
    key: str
    stage: Stage
    config: BaseModel


def plan_stages(
    problem: Problem,
    kind: SubmissionKind,
    language: LanguageModule,
    keys: Sequence[str] | None = None,
) -> list[_Planned]:
    """Resolve stage plugins and validate their configs before anything runs."""
    if keys is None:
        keys = getattr(problem.pipelines.practice, kind)
    planned = []
    for key in keys:
        raw = problem.stages[key]
        plugin = language.stages.get(raw.type)
        if plugin is None:
            raise PipelineConfigError(
                f"stage {key}: language {language.name} has no stage type {raw.type!r}"
            )
        try:
            config = plugin.config_model.model_validate(raw.model_extra or {})
        except ValidationError as error:
            raise PipelineConfigError(f"stage {key}: {error}") from error
        planned.append(_Planned(key, plugin(), config))
    return planned


def run_pipeline(
    job: Job,
    language: LanguageModule,
    executor: Executor,
    sink: EventSink,
    resource_classes: ResourceClasses,
    cancel: threading.Event | None = None,
    on_artifact: ArtifactSink | None = None,
    cancel_note: Callable[[], str] = lambda: "cancelled",
    build_cache: BuildCache = NO_CACHE,
) -> list[StageResult]:
    """Run the stages; `on_artifact` gets the files a stage keeps for the user (e.g. FST),
    `cancel_note` says in the console of the running stage why it was cancelled, `build_cache`
    keeps what the stages build for later checks of the same code."""
    cancel = cancel or threading.Event()
    planned = plan_stages(job.problem, job.kind, language, job.stages)
    finished: dict[str, FinishedStage] = {}
    results: list[StageResult] = []
    skip: SkipReason | None = None
    for ordinal, item in enumerate(planned):
        if skip is None and cancel.is_set():
            skip = "cancelled"
        if skip is not None:
            result = StageResult(
                key=item.key,
                type=item.stage.stage_type,
                ordinal=ordinal,
                status="skipped",
                summary=StageSummary(skip_reason=skip),
            )
            outputs: Mapping[str, bytes] = {}
        else:
            ctx = StageContext(
                key=item.key,
                type=item.stage.stage_type,
                ordinal=ordinal,
                config=item.config,
                problem=job.problem,
                package_dir=job.package_dir,
                kind=job.kind,
                seed=job.seed,
                solution=job.solution,
                limits=stage_limits(job.problem, item.key, item.stage.stage_type, resource_classes),
                previous=dict(finished),
                build_cache=build_cache,
                trace=job.trace,
            )
            result, outcome = _run_stage(item.stage, ctx, executor, sink, cancel, cancel_note)
            outputs = outcome.outputs if outcome else {}
            if outcome is not None and on_artifact is not None:
                for name, data in outcome.artifacts.items():
                    on_artifact(item.key, name, data)
        finished[item.key] = FinishedStage(result, outputs)
        results.append(result)
        sink.emit(StageEndEvent(result=result))
        if skip is None:
            if result.status == "cancelled":
                skip = "cancelled"
            elif result.status in ("failed", "error"):
                skip = "previous_failed"
    sink.emit(DoneEvent())
    return results


def _run_stage(
    stage: Stage,
    ctx: StageContext,
    executor: Executor,
    sink: EventSink,
    cancel: threading.Event,
    cancel_note: Callable[[], str],
) -> tuple[StageResult, StageOutcome | None]:
    sink.emit(StageStartEvent(stage=ctx.key, stage_type=ctx.type, ordinal=ctx.ordinal))
    started_at, started = datetime.now(UTC), time.monotonic()
    runs: list[ExecResult] = []
    fresh: list[tuple[str, ExecResult]] = []  # runs of deterministic plans, for the stage cache

    def finish(outcome: StageOutcome | None) -> StageResult:
        """The stage result; no outcome means the stage was cancelled."""
        return StageResult(
            key=ctx.key,
            type=ctx.type,
            ordinal=ctx.ordinal,
            status=outcome.status if outcome else "cancelled",
            failure_kind=outcome.failure_kind if outcome else None,
            limit=outcome.limit if outcome else None,
            error_code=outcome.error_code if outcome else None,
            started_at=started_at,
            duration_ms=round((time.monotonic() - started) * 1000),
            metrics_schema=stage.metrics_schema,
            metrics=outcome.metrics if outcome else {},
            cached=outcome is not None and (outcome.cached or any(run.cached for run in runs)),
            summary=outcome.summary if outcome else StageSummary(),
        )

    def error(code: str, message: str) -> tuple[StageResult, StageOutcome | None]:
        sink.emit(LogEvent(stage=ctx.key, ch="sys", text=message))
        return finish(StageOutcome(status="error", error_code=code)), None

    try:
        step: StageOutcome | StagePlan = stage.plan(ctx)
        while isinstance(step, StagePlan):
            if len(runs) == MAX_RUNS_PER_STAGE:
                return error("STAGE_RUNS_EXCEEDED", f"more than {MAX_RUNS_PER_STAGE} runs")
            on_line = _line_handler(ctx.key, step, sink)
            if step.note is not None:
                sink.emit(LogEvent(stage=ctx.key, ch="sys", text=step.note))
            key = plan_key(ctx.type, step) if step.cache else None
            run = _cached_run(ctx.build_cache, key) if key is not None else None
            if run is not None:
                sink.emit(LogEvent(stage=ctx.key, ch="sys", text=CACHED_RUN_NOTE))
                for line in run.output.split("\n")[:-1]:
                    on_line("out", line)
            else:
                # Follow-up runs work on what the first one left (e.g. the built simulator).
                run = executor.run(ctx.key, step, on_line, cancel, reuse_dir=bool(runs))
                if key is not None and not _stopped(run):
                    fresh.append((key, run))
            runs.append(run)
            if run.cancelled:
                sink.emit(LogEvent(stage=ctx.key, ch="sys", text=cancel_note()))
                return finish(None), None
            if run.memory_exceeded:  # the sandbox is gone: no interpretation, no follow-up run
                return finish(
                    StageOutcome(status="failed", failure_kind="limit", limit="memory")
                ), None
            if run.output_limited:
                sink.emit(TruncatedEvent(stage=ctx.key, limit_kb=step.output_limit // 1024))
            step = stage.interpret(ctx, runs)
    except ExecutorError as exc:
        return error("EXECUTOR_FAILED", str(exc))
    except Exception:  # a broken plugin must not take the pipeline down
        return error("STAGE_CRASHED", traceback.format_exc(limit=5))
    if _deterministic(step):
        for key, run in fresh:
            _keep_run(ctx.build_cache, key, run)
    return finish(step), step


# --- the stage cache of deterministic plans ----------------------------------------------------


class _Stored(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class _StoredCommand(_Stored):
    argv: list[str]
    exit_code: int | None
    duration_s: float


class _StoredRun(_Stored):
    """A run in the stage cache. The cache is shared storage: it is read back strictly, and
    anything else is a miss. Files are base64."""

    version: Literal[1]
    commands: list[_StoredCommand]
    output: str
    files: dict[str, str]
    oversized: list[str]


def _stopped(run: ExecResult) -> bool:
    return run.timed_out or run.output_limited or run.cancelled or run.memory_exceeded


def _deterministic(outcome: StageOutcome) -> bool:
    """What the same code always gets: not a limit, which depends on the sandbox, and not an
    error of the platform or of the problem."""
    if outcome.status == "failed":
        return outcome.failure_kind != "limit"
    return outcome.status in ("passed", "warning")


def _cached_run(cache: BuildCache, key: str) -> ExecResult | None:
    data = cache.get(key)
    if data is None:
        return None
    try:
        stored = _StoredRun.model_validate_json(data)
        files = {name: base64.b64decode(text, validate=True) for name, text in stored.files.items()}
    except (ValidationError, binascii.Error, ValueError):
        return None
    return ExecResult(
        commands=tuple(
            CommandResult(tuple(c.argv), c.exit_code, c.duration_s) for c in stored.commands
        ),
        output=stored.output,
        files=files,
        oversized=frozenset(stored.oversized),
        cached=True,
    )


def _keep_run(cache: BuildCache, key: str, run: ExecResult) -> None:
    stored = _StoredRun(
        version=1,
        commands=[
            _StoredCommand(argv=list(c.argv), exit_code=c.exit_code, duration_s=c.duration_s)
            for c in run.commands
        ],
        output=run.output,
        files={name: base64.b64encode(data).decode() for name, data in run.files.items()},
        oversized=sorted(run.oversized),
    )
    data = stored.model_dump_json().encode()
    if len(data) <= CACHED_RUN_LIMIT:
        cache.put(key, data)


def _line_handler(stage_key: str, plan: StagePlan, sink: EventSink) -> OnLine:
    def on_line(channel: Channel, text: str) -> None:
        shown, test = (text, None) if plan.line_filter is None else plan.line_filter(text)
        if shown is not None:
            sink.emit(LogEvent(stage=stage_key, ch=channel, text=shown))
        if test is not None:
            sink.emit(TestEvent(stage=stage_key, test=test))

    return on_line
