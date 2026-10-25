"""`precheck` stage (specs/07 §2.1, FR-JDG-02): static check of the solution with pyslang.

The check itself parses untrusted code, so it runs in the sandbox (`sandbox/precheck_runner.py`,
uploaded with the job). This side prepares the job from the problem interface and interprets the
runner's files as untrusted. The canonical text becomes `solution.sv` of all later stages and its
sha256 is the `code_hash` of build and result caches. The normalized AST hash (specs/07 §6) comes
from the runner: it needs the syntax tree, and the tree of untrusted code is built only there.
"""

import hashlib
import json
from collections.abc import Sequence
from importlib import resources
from typing import Annotated, ClassVar, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveInt,
    StringConstraints,
    ValidationError,
)

from judge.core.stage import (
    Command,
    Diagnostic,
    ExecResult,
    FailureKind,
    LimitKind,
    StageContext,
    StageOutcome,
    StagePlan,
    StageSummary,
)
from judge.languages.systemverilog.stages.common import SOLUTION

RUNNER = "precheck_runner.py"
CANONICAL = "canonical.sv"
RESULT = "result.json"
RESULT_LIMIT = 1 << 20
OOM_KILLED = 137  # SIGKILL: the memory limit of the sandbox
# n<normalization version>:<sha256>
AstHash = Annotated[str, StringConstraints(pattern=r"^n[1-9][0-9]{0,3}:[0-9a-f]{64}$")]


class PrecheckConfig(BaseModel):
    """`stages.<key>` of type precheck; the defaults are the platform limits (NFR-LIM-01)."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    max_bytes: PositiveInt = 64 * 1024
    max_lines: PositiveInt = 2000
    max_state_bits: PositiveInt = 1 << 20
    max_generate_steps: PositiveInt = 10_000
    max_constexpr_steps: PositiveInt = 100_000


class _Untrusted(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class RunnerFinding(_Untrusted):
    category: Literal["forbidden", "compile", "limit"]
    code: Annotated[str, Field(max_length=64)]
    message: Annotated[str, Field(max_length=2000)]
    line: PositiveInt
    col: PositiveInt
    limit: Literal["size", "memory"] | None = None


class RunnerResult(_Untrusted):
    v: Literal[1]
    findings: Annotated[list[RunnerFinding], Field(max_length=200)]
    module: str | None
    ports_ok: bool | None
    state_bits: NonNegativeInt | None
    ast_hash: AstHash | None


class PrecheckMetrics(BaseModel):
    """`precheck/v1` (specs/04 §5)."""

    code_hash: str
    ast_hash: str
    normalization_version: int
    module: str
    ports_ok: bool
    state_bits: int


def runner_source() -> bytes:
    return resources.files("judge.languages.systemverilog.sandbox").joinpath(RUNNER).read_bytes()


def job_json(ctx: StageContext, config: PrecheckConfig) -> bytes:
    interface = ctx.problem.interface
    job = {
        "top": ctx.problem.top,
        "parameters": [
            {"name": p.name, "type": p.type, "default": p.default} for p in interface.parameters
        ],
        "ports": [
            {"name": p.name, "dir": p.dir, "width": p.width, "signed": p.signed}
            for p in interface.ports
        ],
        "limits": config.model_dump(),
    }
    return json.dumps(job, ensure_ascii=False).encode()


def _failed(kind: FailureKind, *, limit: LimitKind | None = None) -> StageOutcome:
    return StageOutcome(status="failed", failure_kind=kind, limit=limit)


class PrecheckStage:
    stage_type: ClassVar[str] = "precheck"
    config_model: ClassVar[type[BaseModel]] = PrecheckConfig
    metrics_schema: ClassVar[str | None] = "precheck/v1"

    def plan(self, ctx: StageContext) -> StagePlan:
        assert isinstance(ctx.config, PrecheckConfig)
        return StagePlan(
            # -I: the runner sees neither the environment nor files next to it as modules.
            commands=(Command(("python3", "-I", RUNNER, "job.json", SOLUTION)),),
            timeout_s=ctx.limits.timeout_s,
            output_limit=ctx.limits.output_bytes,
            inputs={
                RUNNER: runner_source(),
                "job.json": job_json(ctx, ctx.config),
                SOLUTION: ctx.solution,
            },
            collect=(RESULT, CANONICAL),
            collect_limit=max(RESULT_LIMIT, ctx.config.max_bytes),
        )

    def interpret(self, ctx: StageContext, runs: Sequence[ExecResult]) -> StageOutcome | StagePlan:
        run = runs[-1]
        if run.timed_out:
            return _failed("limit", limit="time")
        if run.output_limited:
            return _failed("limit", limit="output")
        if run.commands[-1].exit_code == OOM_KILLED:
            return _failed("limit", limit="memory")
        if not run.ok or RESULT not in run.files:
            return StageOutcome(status="error", error_code="TOOL_FAILED")
        try:
            result = RunnerResult.model_validate_json(run.files[RESULT])
        except ValidationError:
            return StageOutcome(status="error", error_code="OUTPUT_INVALID")
        if result.findings:
            return _rejected(result.findings)
        canonical = run.files.get(CANONICAL)
        if (
            canonical is None
            or result.module is None
            or result.ports_ok is not True
            or result.ast_hash is None
        ):
            return StageOutcome(status="error", error_code="OUTPUT_INVALID")
        metrics = PrecheckMetrics(
            code_hash=hashlib.sha256(canonical).hexdigest(),
            ast_hash=result.ast_hash,
            normalization_version=int(result.ast_hash[1 : result.ast_hash.index(":")]),
            module=result.module,
            ports_ok=result.ports_ok,
            state_bits=result.state_bits or 0,
        )
        return StageOutcome(
            status="passed", metrics=metrics.model_dump(), outputs={SOLUTION: canonical}
        )


def _rejected(findings: list[RunnerFinding]) -> StageOutcome:
    diagnostics = [
        Diagnostic(
            severity="error",
            code=f.code,
            file=SOLUTION,
            line=f.line,
            col=f.col,
            message=f.message,
        )
        for f in findings
    ]
    categories = {f.category for f in findings}
    summary = StageSummary(diagnostics=diagnostics)
    if "forbidden" in categories:
        return StageOutcome(status="failed", failure_kind="forbidden", summary=summary)
    if "compile" in categories:
        return StageOutcome(status="failed", failure_kind="compile", summary=summary)
    limit = next(f.limit for f in findings if f.category == "limit")
    return StageOutcome(status="failed", failure_kind="limit", limit=limit, summary=summary)
