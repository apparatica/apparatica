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

from judge.core.limits import StageLimits
from judge.core.package import Problem

StageStatus = Literal[
    "pending", "running", "passed", "warning", "failed", "skipped", "cancelled", "error"
]
FailureKind = Literal["forbidden", "compile", "wrong", "limit"]
LimitKind = Literal["time", "memory", "output", "fst", "cycles"]
SkipReason = Literal["previous_failed", "not_in_pipeline", "cancelled"]
SubmissionKind = Literal["run", "submit"]
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
    """What `Stage.interpret` decides. `outputs` are files handed to the following stages."""

    status: Literal["passed", "warning", "failed", "error"]
    failure_kind: FailureKind | None = None
    limit: LimitKind | None = None
    error_code: str | None = None
    metrics: dict[str, Any] = {}
    summary: StageSummary = StageSummary()
    outputs: dict[str, bytes] = {}

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.status == "failed") != (self.failure_kind is not None):
            raise ValueError("failure_kind is set exactly for failed stages")
        if (self.status == "error") != (self.error_code is not None):
            raise ValueError("error_code is set exactly for stages with an error")
        if self.limit is not None and self.failure_kind != "limit":
            raise ValueError("limit is set only with failure_kind=limit")
        return self


class StageResult(_Model):
    """A finished stage as the worker reports it (`stage_results`, specs/04 §4)."""

    key: str
    type: str
    ordinal: int
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


# A stage's view of one console line: the text to show (None hides it) and a test progress update.
LineFilter = Callable[[str], tuple[str | None, TestCase | None]]


@dataclass(frozen=True)
class Command:
    argv: tuple[str, ...]


@dataclass(frozen=True)
class StagePlan:
    """Commands to run in a fresh stage directory, in order, until one exits non-zero.

    `inputs` are written into the directory first; `collect` names files read back afterwards,
    each at most `collect_limit` bytes. `timeout_s` and `output_limit` cover the whole plan.
    """

    commands: tuple[Command, ...]
    timeout_s: float
    output_limit: int
    inputs: Mapping[str, bytes] = field(default_factory=dict)
    collect: tuple[str, ...] = ()
    collect_limit: int = 1 << 20
    line_filter: LineFilter | None = None


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
    files: Mapping[str, bytes] = field(default_factory=dict)  # collected files that exist
    oversized: frozenset[str] = frozenset()  # collected files over the limit, not read

    @property
    def ok(self) -> bool:
        """Every command ran and exited with 0."""
        return not (self.timed_out or self.output_limited or self.cancelled) and all(
            c.exit_code == 0 for c in self.commands
        )


class Stage(Protocol):
    stage_type: ClassVar[str]  # the `type` of stages.<key> in problem.yaml
    config_model: ClassVar[type[BaseModel]]  # validates stages.<key> of problem.yaml
    metrics_schema: ClassVar[str | None]

    def plan(self, ctx: StageContext) -> StagePlan: ...

    def interpret(self, ctx: StageContext, runs: Sequence[ExecResult]) -> StageOutcome | StagePlan:
        """Decide the outcome from the runs so far, or ask for one more run (e.g. a trace)."""
        ...
