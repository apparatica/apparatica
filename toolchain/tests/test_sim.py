"""The SystemVerilog pipeline `precheck → lint → sim` end to end in the image."""

from pathlib import Path

from judge.core import events
from judge.core.events import Event
from judge.core.executor import LocalDockerExecutor
from judge.core.limits import load_resource_classes, sandbox_limits
from judge.core.package import load_manifest
from judge.core.pipeline import Job, run_pipeline
from judge.core.registry import get_language
from judge.core.stage import StageResult, SubmissionKind
from sandbox import IMAGE

ROOT = Path(__file__).parents[2]
PACKAGE = ROOT / "judge" / "tests" / "data" / "packages" / "counter"
RESOURCE_CLASSES = load_resource_classes(ROOT / "config" / "resource-classes.yaml")

HEADER = (
    "module counter (input logic clk, input logic rst, input logic en,\n"
    "                output logic [3:0] count);\n"
)
CORRECT = HEADER + (
    "  always_ff @(posedge clk)\n"
    "    if (rst) count <= '0;\n"
    "    else if (en) count <= count == 4'd9 ? '0 : count + 4'd1;\n"
    "endmodule\n"
)
NO_WRAP = CORRECT.replace("count == 4'd9 ? '0 : count + 4'd1", "count + 4'd1")  # fails t2
IGNORES_EN = CORRECT.replace("else if (en)", "else")  # fails only the hidden test


class Run:
    def __init__(self, solution: str, kind: SubmissionKind) -> None:
        self.events: list[Event] = []
        self.artifacts: dict[tuple[str, str], bytes] = {}
        problem = load_manifest(PACKAGE)
        job = Job(problem, PACKAGE, kind, seed=41917, solution=solution.encode())
        with LocalDockerExecutor(IMAGE, sandbox_limits(problem, RESOURCE_CLASSES)) as executor:
            self.results = run_pipeline(
                job,
                get_language("systemverilog"),
                executor,
                self,
                RESOURCE_CLASSES,
                on_artifact=self.keep,
            )

    def emit(self, event: Event) -> None:
        self.events.append(event)

    def keep(self, stage: str, name: str, data: bytes) -> None:
        self.artifacts[(stage, name)] = data

    @property
    def sim(self) -> StageResult:
        return self.results[-1]


def test_correct_solution_is_accepted_on_submit() -> None:
    run = Run(CORRECT, "submit")
    assert [(r.key, r.status) for r in run.results] == [
        ("precheck", "passed"),
        ("lint", "passed"),
        ("sim_full", "passed"),
    ]
    assert run.sim.metrics["tests_total"] == 3
    assert run.sim.metrics["tests_passed"] == 3
    assert run.sim.metrics["seed"] == 41917
    assert [(t.id, t.status) for t in run.sim.summary.tests] == [("t1", "passed"), ("t2", "passed")]
    hidden = run.sim.summary.hidden_tests
    assert hidden is not None
    assert (hidden.total, hidden.passed, hidden.failed_index) == (1, 1, None)
    tests = [e.test for e in run.events if isinstance(e, events.TestEvent)]
    assert ("hidden-1", "", "running") in [(t.id, t.name, t.status) for t in tests]
    assert all(t.id != "h1" and "случайный" not in t.name for t in tests)


def test_open_failure_with_trace_window() -> None:
    run = Run(NO_WRAP, "run")
    sim = run.sim
    assert (sim.key, sim.status, sim.failure_kind) == ("sim_run", "failed", "wrong")
    t1, t2 = sim.summary.tests
    assert (t1.status, t2.status) == ("passed", "failed")
    mismatch = t2.mismatches[0]
    assert (mismatch.signal, mismatch.expected, mismatch.actual) == ("count", "4'h0", "4'ha")
    assert mismatch.hint == "После 9 счётчик возвращается в 0"
    failure = sim.metrics["first_failure"]
    assert failure == {"test": "t2", "cycle": t2.cycle, "signal": "count"}
    assert sim.metrics["trace"] == "recorded"
    start, stop = sim.metrics["trace_window"]
    assert (start, stop) == (max(0, failure["cycle"] - 64), failure["cycle"] + 16)
    fst = run.artifacts[("sim_run", "trace.fst")]
    assert fst[:1] == b"\x00"  # FST header block
    assert sim.summary.caption == f"упал тест переход через 9, такт {failure['cycle']}"


def test_hidden_failure_is_not_traced_and_stays_anonymous() -> None:
    run = Run(IGNORES_EN, "submit")
    sim = run.sim
    assert (sim.status, sim.failure_kind) == ("failed", "wrong")
    assert [t.status for t in sim.summary.tests] == ["passed", "passed"]
    hidden = sim.summary.hidden_tests
    assert hidden is not None
    assert (hidden.total, hidden.passed, hidden.failed_index) == (1, 0, 1)
    assert sim.metrics["first_failure"]["test"] == "hidden-1"
    assert "trace" not in sim.metrics
    assert run.artifacts == {}
