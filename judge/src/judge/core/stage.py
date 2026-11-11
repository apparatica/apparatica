"""Stage plugin interface and stage results (specs/07 §2, specs/04 §3.2-3.3).

A stage is a plugin of a language module. The core knows only its `type`, the generic result below
(status, failure kind, metrics as JSON, diagnostics, tests) and what to run: a stage plans commands
for the executor and interprets what they produced. Everything a stage runs is untrusted.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from judge.core.cache import NO_CACHE, BuildCache
from judge.core.limits import StageLimits
from judge.core.package import Problem, instance_key

StageStatus = Literal[
    "pending", "running", "passed", "warning", "failed", "skipped", "cancelled", "error"
]
FailureKind = Literal["forbidden", "compile", "wrong", "limit"]
LimitKind = Literal["time", "memory", "output", "fst", "cycles", "size"]
SkipReason = Literal["previous_failed", "not_in_pipeline", "cancelled"]
SubmissionKind = Literal["run", "submit"]
# What a failed check traces: a window around the first mismatch, or the whole test it is in.
TraceScope = Literal["failure_window", "full_test"]
Channel = Literal["out", "err", "sys"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Diagnostic(_Model):
    """A tool message in the common format (ADR-0011): editor markers and console links."""

    severity: Literal["error", "warning", "info"]
    message: str
    code: str | None = None
    file: str | None = None
    line: int | None = None
    col: int | None = None
    end_line: int | None = None
    end_col: int | None = None


class Mismatch(_Model):
    signal: str
    cycle: int
    expected: str
    actual: str
    hint: str | None = None


class TestCase(_Model):
    id: str
    name: str
    group: str
    status: Literal["passed", "failed", "running", "not_run"]
    duration_ms: int | None = None
    cycle: int | None = Field(default=None, description="Cycle of the first mismatch")
    mismatches: list[Mismatch] = []


class HiddenTests(_Model):
    total: int
    passed: int
    failed_index: int | None = None


class StageSummary(_Model):
    caption: str | None = Field(default=None, description="Pipeline block caption")
    skip_reason: SkipReason | None = None
    diagnostics: list[Diagnostic] = []
    tests: list[TestCase] = []
    hidden_tests: HiddenTests | None = None


class StageOutcome(_Model):
    """What `Stage.interpret` decides. `outputs` are files handed to the following stages;
    `artifacts` are files to keep for the user (FST trace, reports), not passed on; `cached`: the
    stage reused what an earlier check built (the build cache) instead of building it again."""

    status: Literal["passed", "warning", "failed", "error"]
    failure_kind: FailureKind | None = None
    limit: LimitKind | None = None
    error_code: str | None = None
    metrics: dict[str, Any] = {}
    summary: StageSummary = StageSummary()
    outputs: dict[str, bytes] = {}
    artifacts: dict[str, bytes] = {}
    cached: bool = False

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.status == "failed") != (self.failure_kind is not None):
            raise ValueError("failure_kind is set exactly for failed stages")
        if (self.status == "error") != (self.error_code is not None):
            raise ValueError("error_code is set exactly for stages with an error")
        if self.limit is not None and self.failure_kind != "limit":
            raise ValueError("limit is set only with failure_kind=limit")
        return self


class ParamSet(_Model):
    """The parameter set of a stage instance (ADR-0014, specs/06 §2).

    A stage checked at several sets runs as one instance per set; the core knows of a set only
    the names and the values of the parameters, the language module passes them to the tools."""

    id: str = Field(
        pattern=r"^[a-z][a-z0-9_]*$",
        description="`default`: the primary set, the default values of the interface",
        examples=["narrow"],
    )
    values: dict[str, int | str] = Field(
        description="Every parameter of the interface at this set, in the order of the interface:"
        " an integer or a numeric literal of the language, as problem.yaml gives it",
        examples=[{"WIDTH": 1, "DEPTH": 2}],
    )


class StageResult(_Model):
    """A finished stage as the worker reports it (`stage_results`, specs/04 §4)."""

    key: str = Field(
        description="Key of the stage instance: the stage key, or `<stage key>@<set id>` at an"
        " extra parameter set (specs/06 §2)",
        examples=["sim_full@narrow"],
    )
    type: str
    ordinal: int
    param_set: ParamSet | None = Field(
        default=None,
        description="Set of a stage checked at several parameter sets, the primary one included;"
        " null: the stage runs at the primary set only",
    )
    status: StageStatus
    failure_kind: FailureKind | None = None
    limit: LimitKind | None = None
    error_code: str | None = None
    started_at: datetime | None = None
    duration_ms: int | None = None
    metrics_schema: str | None = None
    metrics: dict[str, Any] = {}
    cached: bool = False
    summary: StageSummary = StageSummary()


@dataclass(frozen=True)
class FinishedStage:
    result: StageResult
    outputs: Mapping[str, bytes]


@dataclass(frozen=True)
class StageContext:
    """What a stage instance gets. `key` is the instance key; `param_set` is the set of the
    instance, the primary one for a stage at the primary set only; `previous` holds the finished
    instances by key."""

    key: str
    type: str
    ordinal: int
    config: BaseModel
    problem: Problem
    package_dir: Path
    kind: SubmissionKind
    seed: int
    solution: bytes
    limits: StageLimits
    previous: Mapping[str, FinishedStage]
    param_set: ParamSet
    build_cache: BuildCache = NO_CACHE
    trace: TraceScope = "failure_window"

    def instance(self, stage_key: str) -> str:
        """Key of the instance of another stage at the set of this one, e.g. the `synth` whose
        netlist this `netlist_sim@narrow` simulates (ADR-0014)."""
        return instance_key(stage_key, self.param_set.id)


# A stage's view of one console line: the text to show (None hides it) and a test progress update.
LineFilter = Callable[[str], tuple[str | None, TestCase | None]]


@dataclass(frozen=True)
class Command:
    argv: tuple[str, ...]


@dataclass(frozen=True)
class StagePlan:
    """Commands to run in a fresh stage directory, in order, until one exits non-zero.

    `inputs` are written into the directory first, those named in `executable` with the executable
    bit; `collect` names files read back afterwards, each at most `collect_limit` bytes. `timeout_s`
    and `output_limit` cover the whole plan. `note` goes to the console before the commands run.
    `cache`: the plan is deterministic (FR-JDG-11) — its run is kept in the stage cache by
    `plan_key` and replayed for the same plan instead of running again, so it must name everything
    it reads in `commands` and `inputs` and leave nothing a later plan of the stage needs.
    """

    commands: tuple[Command, ...]
    timeout_s: float
    output_limit: int
    inputs: Mapping[str, bytes] = field(default_factory=dict)
    executable: frozenset[str] = frozenset()
    collect: tuple[str, ...] = ()
    collect_limit: int = 1 << 20
    line_filter: LineFilter | None = None
    note: str | None = None
    cache: bool = False


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    exit_code: int | None  # None: killed (timeout, output limit, cancellation)
    duration_s: float


@dataclass(frozen=True)
class ExecResult:
    commands: tuple[CommandResult, ...]
    output: str  # console text up to the output limit, channels merged
    timed_out: bool = False
    output_limited: bool = False
    cancelled: bool = False
    # The memory limit killed the sandbox whole (gVisor): the stage fails with limit memory.
    memory_exceeded: bool = False
    files: Mapping[str, bytes] = field(default_factory=dict)  # collected files that exist
    oversized: frozenset[str] = frozenset()  # collected files over the limit, not read
    cached: bool = False  # replayed from the stage cache, not run (StagePlan.cache)

    @property
    def ok(self) -> bool:
        """Every command ran and exited with 0."""
        stopped = self.timed_out or self.output_limited or self.cancelled or self.memory_exceeded
        return not stopped and all(c.exit_code == 0 for c in self.commands)


class Stage(Protocol):
    stage_type: ClassVar[str]  # the `type` of stages.<key> in problem.yaml
    config_model: ClassVar[type[BaseModel]]  # validates stages.<key> of problem.yaml
    metrics_schema: ClassVar[str | None]

    def plan(self, ctx: StageContext) -> StagePlan: ...

    def interpret(self, ctx: StageContext, runs: Sequence[ExecResult]) -> StageOutcome | StagePlan:
        """Decide the outcome from the runs so far, or ask for one more run (e.g. a trace)."""
        ...
