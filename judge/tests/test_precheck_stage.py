import hashlib
import json
from pathlib import Path

import pytest
from core_helpers import RESOURCE_CLASSES, make_problem

from judge.core.limits import stage_limits
from judge.core.registry import get_language
from judge.core.stage import CommandResult, ExecResult, StageContext
from judge.languages.systemverilog.sandbox import precheck_runner as runner
from judge.languages.systemverilog.stages.precheck import PrecheckConfig, PrecheckStage

PORTS = [
    {"name": "clk", "dir": "input", "width": "1"},
    {"name": "a", "dir": "input", "width": "WIDTH"},
    {"name": "y", "dir": "output", "width": "WIDTH"},
]
GOOD = (
    "module top #(parameter int WIDTH = 8) (input logic clk, input logic [WIDTH-1:0] a,\n"
    "  output logic [WIDTH-1:0] y);\n  assign y = a; // pass through\nendmodule\n"
)


def context(solution: str, config: PrecheckConfig | None = None) -> StageContext:
    problem = make_problem(
        {"precheck": {"type": "precheck"}},
        run=["precheck"],
        top="top",
        interface={"parameters": [{"name": "WIDTH", "type": "int", "default": 8}], "ports": PORTS},
    )
    return StageContext(
        key="precheck",
        type="precheck",
        ordinal=0,
        config=config or PrecheckConfig(),
        problem=problem,
        package_dir=Path(),
        kind="run",
        seed=1,
        solution=solution.encode(),
        limits=stage_limits(problem, "precheck", "precheck", RESOURCE_CLASSES),
        previous={},
    )


def execute(ctx: StageContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ExecResult:
    """What the sandbox does with the plan, in-process: write the inputs, run the runner."""
    plan = PrecheckStage().plan(ctx)
    for name, content in plan.inputs.items():
        (tmp_path / name).write_bytes(content)
    monkeypatch.chdir(tmp_path)
    exit_code = runner.main(["runner", *plan.commands[0].argv[-2:]])
    files = {n: (tmp_path / n).read_bytes() for n in plan.collect if (tmp_path / n).exists()}
    return ExecResult((CommandResult(plan.commands[0].argv, exit_code, 0.1),), "", files=files)


def interpret(ctx: StageContext, run: ExecResult):  # type: ignore[no-untyped-def]
    return PrecheckStage().interpret(ctx, [run])


def test_registered_in_the_language_module() -> None:
    assert get_language("systemverilog").stages["precheck"] is PrecheckStage


def test_plan_uploads_the_runner_and_the_job() -> None:
    ctx = context(GOOD)
    plan = PrecheckStage().plan(ctx)
    assert plan.commands[0].argv == (
        "python3",
        "-I",
        "precheck_runner.py",
        "job.json",
        "solution.sv",
    )
    assert plan.inputs["solution.sv"] == GOOD.encode()
    assert plan.inputs["precheck_runner.py"] == Path(runner.__file__).read_bytes()
    job = json.loads(plan.inputs["job.json"])
    assert job["top"] == "top"
    assert job["parameters"] == [{"name": "WIDTH", "type": "int", "default": 8}]
    assert job["ports"][1] == {"name": "a", "dir": "input", "width": "WIDTH", "signed": False}
    assert job["limits"]["max_bytes"] == 64 * 1024
    assert plan.collect == ("result.json", "canonical.sv")
    assert plan.timeout_s == 10


def test_passing_solution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = context(GOOD)
    outcome = interpret(ctx, execute(ctx, tmp_path, monkeypatch))
    canonical = outcome.outputs["solution.sv"]
    assert outcome.status == "passed"
    assert b"pass through" not in canonical
    assert outcome.metrics == {
        "code_hash": hashlib.sha256(canonical).hexdigest(),
        "module": "top",
        "ports_ok": True,
        "state_bits": 17,
    }


def test_code_hash_ignores_comment_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Comments become spaces of the same length (columns stay), so only their text is ignored.
    other = GOOD.replace("// pass through", "// другой текст")
    hashes = []
    for name, solution in (("1", GOOD), ("2", other)):
        (tmp_path / name).mkdir()
        ctx = context(solution)
        hashes.append(
            interpret(ctx, execute(ctx, tmp_path / name, monkeypatch)).metrics["code_hash"]
        )
    assert hashes[0] == hashes[1]


@pytest.mark.parametrize(
    ("solution", "kind", "limit", "code"),
    [
        (GOOD.replace("assign y = a;", "initial y = 0;"), "forbidden", None, "CONSTRUCT"),
        (GOOD.replace("[WIDTH-1:0] a", "[3:0] a"), "compile", None, "PORT_WIDTH"),
        (GOOD.replace("assign y = a;", "logic [7:0] m [2**24];"), "limit", "memory", "STATE_SIZE"),
    ],
)
def test_rejected_solution(
    solution: str,
    kind: str,
    limit: str | None,
    code: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = context(solution)
    outcome = interpret(ctx, execute(ctx, tmp_path, monkeypatch))
    assert (outcome.status, outcome.failure_kind, outcome.limit) == ("failed", kind, limit)
    diagnostic = outcome.summary.diagnostics[0]
    assert (diagnostic.severity, diagnostic.code, diagnostic.file) == ("error", code, "solution.sv")
    assert outcome.outputs == {}


def test_size_limit_from_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = context(GOOD, PrecheckConfig(max_bytes=50))
    outcome = interpret(ctx, execute(ctx, tmp_path, monkeypatch))
    assert (outcome.failure_kind, outcome.limit) == ("limit", "size")


def fake_run(exit_code: int | None = 0, **files: bytes) -> ExecResult:
    return ExecResult((CommandResult(("python3",), exit_code, 0.1),), "", files=files)


VALID = json.dumps({"v": 1, "findings": [], "module": "top", "ports_ok": True, "state_bits": 1})


@pytest.mark.parametrize(
    ("run", "status", "detail"),
    [
        (ExecResult((CommandResult(("python3",), None, 9.9),), "", timed_out=True), "failed", "time"),
        (ExecResult((CommandResult(("python3",), None, 0.1),), "", output_limited=True), "failed", "output"),
        (fake_run(137), "failed", "memory"),
        (fake_run(1), "error", "TOOL_FAILED"),
        (fake_run(0), "error", "TOOL_FAILED"),
        (fake_run(0, **{"result.json": b"{"}), "error", "OUTPUT_INVALID"),
        (fake_run(0, **{"result.json": b'{"v": 2}'}), "error", "OUTPUT_INVALID"),
        (fake_run(0, **{"result.json": VALID.encode()}), "error", "OUTPUT_INVALID"),  # no canonical
        (fake_run(0, **{"result.json": VALID.replace("true", "false").encode(), "canonical.sv": b"x"}), "error", "OUTPUT_INVALID"),
        (fake_run(0, **{"result.json": VALID.replace('"findings": []', '"findings": [{"category": "x"}]').encode()}), "error", "OUTPUT_INVALID"),
    ],
)  # fmt: skip
def test_untrusted_runner_output(run: ExecResult, status: str, detail: str) -> None:
    outcome = interpret(context(GOOD), run)
    assert outcome.status == status
    assert detail in (outcome.limit, outcome.error_code)
