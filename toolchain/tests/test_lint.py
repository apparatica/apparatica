"""The SystemVerilog pipeline `precheck → lint` end to end in the image."""

from pathlib import Path

import yaml

from judge.core.events import Event, LogEvent
from judge.core.executor import LocalDockerExecutor
from judge.core.limits import load_resource_classes, sandbox_limits
from judge.core.package import Problem, parse_manifest
from judge.core.pipeline import Job, run_pipeline
from judge.core.registry import get_language
from judge.core.stage import StageResult
from sandbox import IMAGE, RUNTIME

ROOT = Path(__file__).parents[2]
RESOURCE_CLASSES = load_resource_classes(ROOT / "config" / "resource-classes.yaml")
HEADER = "module top (input logic clk, input logic [7:0] a, output logic [7:0] y);\n"


def problem() -> Problem:
    manifest = {
        "schema": 1,
        "id": "reg",
        "number": 1,
        "version": 1,
        "leaderboard_epoch": 1,
        "language": "systemverilog",
        "kind": "design",
        "title": "Register",
        "difficulty": "easy",
        "tags": ["reg"],
        "resource_class": "light",
        "top": "top",
        "interface": {
            "ports": [
                {"name": "clk", "dir": "input", "width": "1", "role": "clock"},
                {"name": "a", "dir": "input", "width": "8"},
                {"name": "y", "dir": "output", "width": "8"},
            ]
        },
        "files": {"statement": "statement.md", "template": "template.sv"},
        "stages": {"precheck": {"type": "precheck"}, "lint": {"type": "lint"}},
        "pipelines": {"practice": {"run": ["precheck", "lint"], "submit": ["precheck", "lint"]}},
    }
    return parse_manifest(yaml.safe_dump(manifest), "problem.yaml")


class Sink:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


def judge(solution: str) -> tuple[list[StageResult], Sink]:
    task = problem()
    sink = Sink()
    job = Job(task, Path(), "run", seed=1, solution=solution.encode())
    with LocalDockerExecutor(
        IMAGE, sandbox_limits(task, RESOURCE_CLASSES), runtime=RUNTIME
    ) as executor:
        results = run_pipeline(job, get_language("systemverilog"), executor, sink, RESOURCE_CLASSES)
    return results, sink


def test_clean_solution_passes_both_stages() -> None:
    results, _ = judge(HEADER + "  always_ff @(posedge clk) y <= a;\nendmodule\n")
    assert [(r.key, r.status) for r in results] == [("precheck", "passed"), ("lint", "passed")]
    assert results[1].metrics == {"warnings": 0, "errors": 0, "rules": {}}


def test_warning_points_into_the_user_code() -> None:
    # The comment shifts nothing: lint sees the canonical text with the same lines and columns.
    body = "  /* сдвиг */ logic [3:0] t;\n  always_ff @(posedge clk) y <= a;\n  assign t = a;\n"
    results, sink = judge(HEADER + body + "endmodule\n")
    lint = results[1]
    assert lint.status == "warning"
    width = next(d for d in lint.summary.diagnostics if d.code == "WIDTHTRUNC")
    assert (width.file, width.line) == ("solution.sv", 4)
    console = [e.text for e in sink.events if isinstance(e, LogEvent) and e.stage == "lint"]
    assert any("WIDTHTRUNC" in line for line in console)


def test_forbidden_solution_never_reaches_lint() -> None:
    results, _ = judge(HEADER + "  initial y = 0;\nendmodule\n")
    assert [(r.key, r.status) for r in results] == [("precheck", "failed"), ("lint", "skipped")]
