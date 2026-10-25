"""Pipeline execution: the stages of `pipelines.practice.<kind>` in order (specs/07 §2.7).

A stage after a failed one or after a platform error is skipped; cancellation marks the running
stage cancelled and skips the rest. The pipeline reports stage results; the verdict is aggregated
separately (`judge.core.verdict`) by whoever owns the final status.
"""

import threading
import time
import traceback
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

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
)

# Runs per stage: the first one plus follow-ups such as the trace window of `sim`.
MAX_RUNS_PER_STAGE = 4

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


@dataclass(frozen=True)
class _Planned:
    key: str
    stage: Stage
    config: BaseModel


def plan_stages(problem: Problem, kind: SubmissionKind, language: LanguageModule) -> list[_Planned]:
    """Resolve stage plugins and validate their configs before anything runs."""
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
) -> list[StageResult]:
    """Run the stages; `on_artifact` gets the files a stage keeps for the user (e.g. FST)."""
    cancel = cancel or threading.Event()
    planned = plan_stages(job.problem, job.kind, language)
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
            )
            result, outcome = _run_stage(item.stage, ctx, executor, sink, cancel)
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
) -> tuple[StageResult, StageOutcome | None]:
    sink.emit(StageStartEvent(stage=ctx.key, stage_type=ctx.type, ordinal=ctx.ordinal))
    started_at, started = datetime.now(UTC), time.monotonic()

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
            summary=outcome.summary if outcome else StageSummary(),
        )

    def error(code: str, message: str) -> tuple[StageResult, StageOutcome | None]:
        sink.emit(LogEvent(stage=ctx.key, ch="sys", text=message))
        return finish(StageOutcome(status="error", error_code=code)), None

    runs: list[ExecResult] = []
    try:
        step: StageOutcome | StagePlan = stage.plan(ctx)
        while isinstance(step, StagePlan):
            if len(runs) == MAX_RUNS_PER_STAGE:
                return error("STAGE_RUNS_EXCEEDED", f"more than {MAX_RUNS_PER_STAGE} runs")
            on_line = _line_handler(ctx.key, step, sink)
            # Follow-up runs work on what the first one left (e.g. the built simulator).
            run = executor.run(ctx.key, step, on_line, cancel, reuse_dir=bool(runs))
            runs.append(run)
            if run.cancelled:
                sink.emit(LogEvent(stage=ctx.key, ch="sys", text="cancelled"))
                return finish(None), None
            if run.output_limited:
                sink.emit(TruncatedEvent(stage=ctx.key, limit_kb=step.output_limit // 1024))
            step = stage.interpret(ctx, runs)
    except ExecutorError as exc:
        return error("EXECUTOR_FAILED", str(exc))
    except Exception:  # a broken plugin must not take the pipeline down
        return error("STAGE_CRASHED", traceback.format_exc(limit=5))
    return finish(step), step


def _line_handler(stage_key: str, plan: StagePlan, sink: EventSink) -> OnLine:
    def on_line(channel: Channel, text: str) -> None:
        shown, test = (text, None) if plan.line_filter is None else plan.line_filter(text)
        if shown is not None:
            sink.emit(LogEvent(stage=stage_key, ch=channel, text=shown))
        if test is not None:
            sink.emit(TestEvent(stage=stage_key, test=test))

    return on_line
