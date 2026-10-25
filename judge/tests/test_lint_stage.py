from pathlib import Path

import pytest
from core_helpers import RESOURCE_CLASSES, make_problem

from judge.core.limits import stage_limits
from judge.core.registry import get_language
from judge.core.stage import (
    CommandResult,
    ExecResult,
    FinishedStage,
    StageContext,
    StageOutcome,
    StageResult,
)
from judge.languages.systemverilog.stages.lint import LintConfig, LintStage, parse_sarif

DATA = Path(__file__).parent / "data" / "lint"  # captured from Verilator 5.052 in the image
CANONICAL = b"module top; endmodule\n"
OVERSIZED = frozenset({"lint.sarif"})


def context(config: LintConfig | None = None, *, with_precheck: bool = True) -> StageContext:
    problem = make_problem(
        {"precheck": {"type": "precheck"}, "lint": {"type": "lint"}},
        run=["precheck", "lint"],
        top="top",
    )
    precheck = FinishedStage(
        StageResult(key="precheck", type="precheck", ordinal=0, status="passed"),
        {"solution.sv": CANONICAL},
    )
    return StageContext(
        key="lint",
        type="lint",
        ordinal=1,
        config=config or LintConfig(),
        problem=problem,
        package_dir=Path(),
        kind="run",
        seed=1,
        solution=b"// original\nmodule top; endmodule\n",
        limits=stage_limits(problem, "lint", "lint", RESOURCE_CLASSES),
        previous={"precheck": precheck} if with_precheck else {},
    )


def run_with(
    sarif: str | bytes | None,
    exit_code: int | None = 0,
    *,
    timed_out: bool = False,
    output_limited: bool = False,
) -> ExecResult:
    files = {}
    if sarif is not None:
        files["lint.sarif"] = sarif if isinstance(sarif, bytes) else (DATA / sarif).read_bytes()
    command = CommandResult(("verilator",), exit_code, 0.2)
    return ExecResult(
        (command,), "", timed_out=timed_out, output_limited=output_limited, files=files
    )


def interpret(run: ExecResult, config: LintConfig | None = None) -> StageOutcome:
    outcome = LintStage().interpret(context(config), [run])
    assert isinstance(outcome, StageOutcome)
    return outcome


def test_registered() -> None:
    assert get_language("systemverilog").stages["lint"] is LintStage


def test_plan_lints_the_canonical_text() -> None:
    plan = LintStage().plan(context(LintConfig(flags=["-Wall"])))
    assert plan.inputs == {"solution.sv": CANONICAL}
    assert plan.commands[0].argv == (
        "verilator",
        "--lint-only",
        "-Wno-fatal",
        "-Wall",
        "-Wno-DECLFILENAME",
        "--top-module",
        "top",
        "--diagnostics-sarif",
        "--diagnostics-sarif-output",
        "lint.sarif",
        "solution.sv",
    )
    assert plan.collect == ("lint.sarif",)
    assert plan.timeout_s == 10


def test_plan_needs_precheck() -> None:
    with pytest.raises(LookupError, match="precheck"):
        LintStage().plan(context(with_precheck=False))


@pytest.mark.parametrize("flag", ["-CFLAGS", "--exe", "-Wall;rm", "solution.sv"])
def test_flags_are_warning_options_only(flag: str) -> None:
    with pytest.raises(ValueError, match="flags"):
        LintConfig.model_validate({"flags": [flag]})


@pytest.mark.parametrize("name", ["clean", "error"])
def test_verilator_sarif_defect_is_repaired(name: str) -> None:
    # Verilator 5.052 drops a comma after an empty rule list; the captured files have it.
    data = (DATA / f"{name}.sarif").read_bytes()
    assert b'}            "invocations"' in data
    assert parse_sarif(data).version == "2.1.0"


def test_clean_solution() -> None:
    outcome = interpret(run_with("clean.sarif"))
    assert outcome.status == "passed"
    assert outcome.metrics == {"warnings": 0, "errors": 0, "rules": {}}
    assert outcome.summary.diagnostics == []


def test_warnings() -> None:
    outcome = interpret(run_with("warnings.sarif"))
    assert outcome.status == "warning"
    assert outcome.metrics == {
        "warnings": 2,
        "errors": 0,
        "rules": {"WIDTHTRUNC": 1, "UNUSEDSIGNAL": 1},
    }
    first = outcome.summary.diagnostics[0]
    assert (first.severity, first.code, first.file, first.line, first.col) == (
        "warning",
        "WIDTHTRUNC",
        "solution.sv",
        2,
        30,
    )
    assert first.message.startswith("Operator ASSIGNDLY expects 4 bits")
    assert "For warning description" not in first.message


def test_warnings_fail_when_configured() -> None:
    outcome = interpret(run_with("warnings.sarif"), LintConfig(warnings_fail=True))
    assert (outcome.status, outcome.failure_kind) == ("failed", "compile")


def test_errors_fail_as_compile() -> None:
    outcome = interpret(run_with("error.sarif", exit_code=1))
    assert (outcome.status, outcome.failure_kind) == ("failed", "compile")
    assert outcome.metrics["errors"] >= 1
    error = outcome.summary.diagnostics[0]
    assert (error.severity, error.line, error.col) == ("error", 2, 18)
    assert error.message == "Can't find definition of variable: 'undefined_thing'"


@pytest.mark.parametrize(
    ("run", "status", "detail"),
    [
        (run_with(None, None, timed_out=True), "failed", "time"),
        (run_with(None, None, output_limited=True), "failed", "output"),
        (ExecResult((CommandResult(("v",), 0, 0.1),), "", oversized=OVERSIZED), "failed", "output"),
        (run_with(None, 0), "error", "TOOL_FAILED"),
        (run_with("clean.sarif", 1), "error", "TOOL_FAILED"),  # non-zero exit without errors
        (run_with(b"{not json"), "error", "OUTPUT_INVALID"),
        (run_with(b'{"version": "2.1.0", "runs": []}'), "error", "OUTPUT_INVALID"),
    ],
)  # fmt: skip
def test_untrusted_or_failed_runs(run: ExecResult, status: str, detail: str) -> None:
    outcome = interpret(run)
    assert outcome.status == status
    assert detail in (outcome.limit, outcome.error_code)


def test_diagnostics_are_capped_but_counted() -> None:
    result = (
        '{"level": "warning", "ruleId": "W", "message": {"text": "w"}, '
        '"locations": [{"physicalLocation": {"artifactLocation": {"uri": "file:///w/x.sv"}}}]}'
    )
    sarif = f'{{"version": "2.1.0", "runs": [{{"results": [{", ".join([result] * 250)}]}}]}}'
    outcome = interpret(run_with(sarif.encode()))
    assert outcome.metrics["warnings"] == 250
    assert len(outcome.summary.diagnostics) == 200
    assert outcome.summary.diagnostics[0].file == "x.sv"
