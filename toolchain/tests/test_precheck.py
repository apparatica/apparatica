"""The `precheck` stage end to end: the runner in the image's pyslang, the judge interpreting it."""

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from judge.core.executor import LocalDockerExecutor
from judge.core.limits import SandboxLimits, StageLimits
from judge.core.package import parse_manifest
from judge.core.stage import Command, StageContext, StageOutcome, StagePlan
from judge.languages.systemverilog.stages.precheck import PrecheckConfig, PrecheckStage
from sandbox import IMAGE, RUNTIME

CORPUS = Path(__file__).parents[2] / "judge" / "tests" / "data" / "precheck" / "good"
ADDER = (CORPUS / "adder.sv").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def executor() -> Iterator[LocalDockerExecutor]:
    with LocalDockerExecutor(
        IMAGE, SandboxLimits(cpus=2, memory_mb=2048, pids=256), runtime=RUNTIME
    ) as running:
        yield running


def context(solution: str) -> StageContext:
    manifest = {
        "schema": 1,
        "id": "adder",
        "number": 1,
        "version": 1,
        "leaderboard_epoch": 1,
        "language": "systemverilog",
        "kind": "design",
        "title": "Adder",
        "difficulty": "easy",
        "tags": ["adder"],
        "resource_class": "light",
        "top": "top",
        "interface": {
            "parameters": [{"name": "W", "type": "int", "default": 16}],
            "ports": [
                {"name": "a", "dir": "input", "width": "W"},
                {"name": "b", "dir": "input", "width": "W"},
                {"name": "cin", "dir": "input", "width": "1"},
                {"name": "sum", "dir": "output", "width": "W"},
                {"name": "cout", "dir": "output", "width": "1"},
            ],
        },
        "files": {"statement": "statement.md", "template": "template.sv"},
        "stages": {"precheck": {"type": "precheck"}},
        "pipelines": {"practice": {"run": ["precheck"], "submit": ["precheck"]}},
    }
    return StageContext(
        key="precheck",
        type="precheck",
        ordinal=0,
        config=PrecheckConfig(),
        problem=parse_manifest(yaml.safe_dump(manifest), "problem.yaml"),
        package_dir=Path(),
        kind="run",
        seed=1,
        solution=solution.encode(),
        limits=StageLimits(timeout_s=30, output_bytes=1 << 20, fst_bytes=1 << 20),
        previous={},
    )


def precheck(executor: LocalDockerExecutor, solution: str) -> StageOutcome:
    ctx = context(solution)
    stage = PrecheckStage()
    run = executor.run("precheck", stage.plan(ctx), lambda *_: None, threading.Event())
    outcome = stage.interpret(ctx, [run])
    assert isinstance(outcome, StageOutcome)
    return outcome


def test_corpus_solution_passes(executor: LocalDockerExecutor) -> None:
    assert "module top" in ADDER
    outcome = precheck(executor, ADDER)
    assert outcome.status == "passed", outcome.summary.diagnostics
    assert outcome.metrics["ports_ok"] is True
    assert len(outcome.metrics["code_hash"]) == 64


def test_canonical_text_builds_with_verilator(executor: LocalDockerExecutor) -> None:
    commented = ADDER.replace("\n", " // verilator lint_off WIDTH\n", 3)
    canonical = precheck(executor, commented).outputs["solution.sv"]
    lint = ("verilator", "--lint-only", "-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSEDPARAM")  # 07 §2.2
    plan = StagePlan(
        commands=(Command((*lint, "solution.sv")),),
        timeout_s=60,
        output_limit=1 << 16,
        inputs={"solution.sv": canonical},
    )
    result = executor.run("lint", plan, lambda *_: None, threading.Event())
    assert result.ok, result.output


def test_forbidden_solution_is_rejected(executor: LocalDockerExecutor) -> None:
    solution = '`include "/etc/passwd"\n' + ADDER
    outcome = precheck(executor, solution)
    assert (outcome.status, outcome.failure_kind) == ("failed", "forbidden")
    assert outcome.summary.diagnostics[0].code == "PREPROCESSOR"
