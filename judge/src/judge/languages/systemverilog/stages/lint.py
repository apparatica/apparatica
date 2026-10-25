"""`lint` stage (specs/07 §2.2, FR-JDG-03): Verilator `--lint-only` on the canonical text.

Diagnostics come from Verilator's SARIF file, not from parsing its console text. Errors fail the
stage as `compile`; warnings make it `warning` (or `failed` with `warnings_fail`) and show up in the
console, the editor and `summary.diagnostics`.
"""

import re
from collections import Counter
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Annotated, ClassVar, Literal
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from judge.core.stage import (
    Command,
    Diagnostic,
    ExecResult,
    StageContext,
    StageOutcome,
    StagePlan,
    StageSummary,
)
from judge.languages.systemverilog.stages.common import SOLUTION, canonical_solution

SARIF = "lint.sarif"
SARIF_LIMIT = 8 << 20
MAX_DIAGNOSTICS = 200  # shown in the summary; metrics count all of them
WarningFlag = Annotated[str, StringConstraints(pattern=r"^-W[A-Za-z0-9_-]+$")]


class LintConfig(BaseModel):
    """`stages.<key>` of type lint. `flags` are Verilator warning options only."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    flags: list[WarningFlag] = ["-Wall", "-Wno-UNUSEDPARAM"]
    warnings_fail: bool = False


class LintMetrics(BaseModel):
    """`lint/v1` (specs/04 §5)."""

    warnings: int
    errors: int
    rules: dict[str, int]


# SARIF 2.1.0, only the parts the stage reads. Unknown fields are ignored: it is a big format.
class _Sarif(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)


class _Region(_Sarif):
    startLine: int | None = None  # noqa: N815 - SARIF field names
    startColumn: int | None = None  # noqa: N815
    endLine: int | None = None  # noqa: N815
    endColumn: int | None = None  # noqa: N815


class _ArtifactLocation(_Sarif):
    uri: str | None = None


class _PhysicalLocation(_Sarif):
    artifactLocation: _ArtifactLocation | None = None  # noqa: N815
    region: _Region | None = None


class _Location(_Sarif):
    physicalLocation: _PhysicalLocation | None = None  # noqa: N815


class _Message(_Sarif):
    text: str = ""


class _Result(_Sarif):
    level: Literal["error", "warning", "note", "none"] = "warning"
    ruleId: str | None = None  # noqa: N815
    message: _Message
    locations: list[_Location] = []


class _Run(_Sarif):
    results: list[_Result] = []


class _Log(_Sarif):
    version: Literal["2.1.0"]
    runs: Annotated[list[_Run], Field(min_length=1)]


# Verilator 5.052 writes no comma after an empty "rules" list, which happens whenever no diagnostic
# has a rule id (a clean run, or errors only). Repaired at exactly that place, then validated.
_EMPTY_RULES = re.compile(rb'("rules":\s*\[\s*\]\s*\}\s*\})(\s*"invocations")')


def parse_sarif(data: bytes) -> _Log:
    try:
        return _Log.model_validate_json(data)
    except ValidationError:
        repaired, count = _EMPTY_RULES.subn(rb"\1,\2", data, count=1)
        if not count:
            raise
        return _Log.model_validate_json(repaired)


_SEVERITY: dict[str, Literal["error", "warning", "info"]] = {
    "error": "error",
    "warning": "warning",
    "note": "info",
    "none": "info",
}


def diagnostic(result: _Result) -> Diagnostic:
    location = result.locations[0].physicalLocation if result.locations else None
    region = location.region if location else None
    uri = location.artifactLocation.uri if location and location.artifactLocation else None
    file = PurePosixPath(unquote(urlparse(uri).path)).name if uri else None
    # Verilator appends "... For warning description see ..." lines: the first line is the message.
    message = result.message.text.split("\n", 1)[0].strip() or "Verilator diagnostic"
    return Diagnostic(
        severity=_SEVERITY[result.level],
        code=result.ruleId,
        file=SOLUTION if file == SOLUTION else file,
        line=region.startLine if region else None,
        col=region.startColumn if region else None,
        end_line=region.endLine if region else None,
        end_col=region.endColumn if region else None,
        message=message,
    )


class LintStage:
    stage_type: ClassVar[str] = "lint"
    config_model: ClassVar[type[BaseModel]] = LintConfig
    metrics_schema: ClassVar[str | None] = "lint/v1"

    def plan(self, ctx: StageContext) -> StagePlan:
        assert isinstance(ctx.config, LintConfig)
        argv = (
            "verilator",
            "--lint-only",
            # Warnings must not change the exit code: the SARIF file says what they are.
            "-Wno-fatal",
            *ctx.config.flags,
            # The file is always solution.sv, whatever the module is called.
            "-Wno-DECLFILENAME",
            "--top-module",
            ctx.problem.top,
            "--diagnostics-sarif",
            "--diagnostics-sarif-output",
            SARIF,
            SOLUTION,
        )
        return StagePlan(
            commands=(Command(argv),),
            timeout_s=ctx.limits.timeout_s,
            output_limit=ctx.limits.output_bytes,
            inputs={SOLUTION: canonical_solution(ctx)},
            collect=(SARIF,),
            collect_limit=SARIF_LIMIT,
        )

    def interpret(self, ctx: StageContext, runs: Sequence[ExecResult]) -> StageOutcome | StagePlan:
        assert isinstance(ctx.config, LintConfig)
        run = runs[-1]
        if run.timed_out:
            return StageOutcome(status="failed", failure_kind="limit", limit="time")
        if run.output_limited or SARIF in run.oversized:
            return StageOutcome(status="failed", failure_kind="limit", limit="output")
        if SARIF not in run.files:
            return StageOutcome(status="error", error_code="TOOL_FAILED")
        try:
            log = parse_sarif(run.files[SARIF])
        except ValidationError:
            return StageOutcome(status="error", error_code="OUTPUT_INVALID")
        diagnostics = [diagnostic(r) for sarif_run in log.runs for r in sarif_run.results]
        errors = sum(d.severity == "error" for d in diagnostics)
        warnings = sum(d.severity == "warning" for d in diagnostics)
        if run.commands[-1].exit_code != 0 and not errors:
            return StageOutcome(status="error", error_code="TOOL_FAILED")
        metrics = LintMetrics(
            warnings=warnings,
            errors=errors,
            rules=dict(Counter(d.code for d in diagnostics if d.code)),
        ).model_dump()
        summary = StageSummary(diagnostics=diagnostics[:MAX_DIAGNOSTICS])
        if errors or (warnings and ctx.config.warnings_fail):
            return StageOutcome(
                status="failed", failure_kind="compile", metrics=metrics, summary=summary
            )
        if warnings:
            return StageOutcome(status="warning", metrics=metrics, summary=summary)
        return StageOutcome(status="passed", metrics=metrics, summary=summary)
