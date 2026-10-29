import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest
from core_helpers import RESOURCE_CLASSES, MemoryCache

from judge.core.cache import BuildCache, NoCache, plan_key
from judge.core.limits import stage_limits
from judge.core.package import load_manifest
from judge.core.registry import get_language
from judge.core.stage import (
    CommandResult,
    ExecResult,
    FinishedStage,
    StageContext,
    StageOutcome,
    StagePlan,
    StageResult,
)
from judge.languages.systemverilog.stages.sim import (
    BINARY_LIMIT,
    CACHED_NOTE,
    SimConfig,
    SimStage,
    trace_signals,
    verilator_seed,
)

PACKAGE = Path(__file__).parent / "data" / "packages" / "counter"
CANONICAL = b"module counter; endmodule\n"
SEED = 41917
BINARY = b"\x7fELF simulator"


def context(
    groups: list[str] | None = None,
    *,
    cache: BuildCache | None = None,
    solution: bytes = CANONICAL,
    **config: Any,
) -> StageContext:
    problem = load_manifest(PACKAGE)
    previous = {
        "precheck": FinishedStage(
            StageResult(key="precheck", type="precheck", ordinal=0, status="passed"),
            {"solution.sv": solution},
        ),
        "synth": FinishedStage(
            StageResult(key="synth", type="synth", ordinal=1, status="passed"),
            {"netlist_generic": b"module counter_net; endmodule\n"},
        ),
    }
    settings = {"testbench": "main", "groups": groups or ["public", "hidden"]} | config
    return StageContext(
        key="sim",
        type="sim",
        ordinal=2,
        config=SimConfig.model_validate(settings),
        problem=problem,
        package_dir=PACKAGE,
        kind="submit",
        seed=SEED,
        solution=b"// original\n",
        limits=stage_limits(problem, "sim_full", "sim", RESOURCE_CLASSES),
        previous=previous,
        build_cache=cache or NoCache(),
    )


def rec(event: str, **fields: Any) -> dict[str, Any]:
    return {"v": 1, "event": event, **fields}


def jsonl(*records: dict[str, Any]) -> bytes:
    return b"".join(json.dumps(r, ensure_ascii=False).encode() + b"\n" for r in records)


START = rec("suite_start", seed=SEED, groups=["public", "hidden"])
TB_ERROR = rec("suite_abort", reason="tb_error", cycle=0, message="duplicate test id t1")


def started(test_id: str, cycle: int, group: str = "public") -> dict[str, Any]:
    return rec("test_start", id=test_id, name=f"тест {test_id}", group=group, cycle=cycle)


def ended(test_id: str, status: str, begin: int, end: int) -> dict[str, Any]:
    return rec("test_end", id=test_id, status=status, cycles=end - begin, cycle=end)


def mismatch(test_id: str, cycle: int) -> dict[str, Any]:
    return rec(
        "mismatch",
        test=test_id,
        cycle=cycle,
        time_ps=cycle * 10_000,
        signal="count",
        expected="4'h0",
        actual="4'ha",
        hint="После 9 — 0",
    )


PASSED = jsonl(
    START,
    started("t1", 0), ended("t1", "passed", 0, 7),
    started("t2", 7), ended("t2", "passed", 7, 21),
    started("h1", 21, "hidden"), ended("h1", "passed", 21, 63),
    rec("suite_end", passed=3, failed=0, not_run=0, cycles=63),
)  # fmt: skip
OPEN_FAIL = jsonl(
    START,
    started("t1", 0), ended("t1", "passed", 0, 7),
    started("t2", 7), mismatch("t2", 18), ended("t2", "failed", 7, 21),
    rec("test_skip", id="h1", name="тест h1", group="hidden"),
    rec("suite_end", passed=1, failed=1, not_run=1, cycles=21),
)  # fmt: skip
HIDDEN_FAIL = jsonl(
    START,
    started("t1", 0), ended("t1", "passed", 0, 7),
    started("t2", 7), ended("t2", "passed", 7, 21),
    started("h1", 21, "hidden"), mismatch("h1", 30), ended("h1", "failed", 21, 63),
    rec("suite_end", passed=2, failed=1, not_run=0, cycles=63),
)  # fmt: skip


def built(
    exit_code: int | None = 0,
    *,
    binary: bytes | None = BINARY,
    output: str = "",
    timed_out: bool = False,
    output_limited: bool = False,
    oversized: frozenset[str] = frozenset(),
) -> ExecResult:
    """The build plan of the stage."""
    return ExecResult(
        (CommandResult(("apx-verilate",), exit_code, 3.0),),
        output,
        timed_out=timed_out,
        output_limited=output_limited,
        files={} if binary is None else {"obj_dir/Vtb_top": binary},
        oversized=oversized,
    )


def run_with(
    result: bytes | None,
    sim: int | None = 0,
    *,
    timed_out: bool = False,
    output_limited: bool = False,
    oversized: frozenset[str] = frozenset(),
    trace: bytes | None = None,
) -> ExecResult:
    """A simulation run of the built binary."""
    collected = {} if trace is None else {"trace.fst": trace}
    if result is not None:
        collected["tb_result.jsonl"] = result
    return ExecResult(
        (CommandResult(("./obj_dir/Vtb_top",), sim, 0.2),),
        "",
        timed_out=timed_out,
        output_limited=output_limited,
        files=collected,
        oversized=oversized,
    )


def interpret(
    ctx: StageContext, *runs: ExecResult, build: ExecResult | None = None
) -> StageOutcome | StagePlan:
    """The runs after a successful build, or of the cached binary without a build."""
    first = [] if ctx.build_cache.get(cache_key(ctx)) else [build or built()]
    return SimStage().interpret(ctx, [*first, *runs])


def outcome_of(ctx: StageContext, *runs: ExecResult) -> StageOutcome:
    outcome = interpret(ctx, *runs)
    assert isinstance(outcome, StageOutcome)
    return outcome


def cache_key(ctx: StageContext) -> str:
    """The key of the build plan: the first plan without a cache."""
    return plan_key("sim", SimStage().plan(dataclasses.replace(ctx, build_cache=NoCache())))


def simulation(ctx: StageContext) -> StagePlan:
    """The plan of the simulation run after the build."""
    plan = interpret(ctx)
    assert isinstance(plan, StagePlan)
    return plan


def test_registered() -> None:
    assert get_language("systemverilog").stages["sim"] is SimStage


def test_plan_builds_first() -> None:
    plan = SimStage().plan(context())
    (build,) = (c.argv for c in plan.commands)
    assert build[:2] == ("apx-verilate", "--quiet")
    assert build[build.index("--x-assign") :][:2] == ("--x-assign", "unique")
    assert build[build.index("--x-initial") :][:2] == ("--x-initial", "unique")
    # apx_tb_pkg first: its macros must be defined before the testbench (specs/06 §3.2).
    assert build[-5:] == (
        "/opt/apx/sv/apx_tb_pkg.sv",
        "pkg/tb/tb_top.sv",
        "solution.sv",
        "--top-module",
        "tb_top",
    )
    assert plan.inputs["solution.sv"] == CANONICAL
    assert plan.inputs["pkg/tb/tb_top.sv"] == (PACKAGE / "tb" / "tb_top.sv").read_bytes()
    assert (plan.collect, plan.collect_limit) == (("obj_dir/Vtb_top",), BINARY_LIMIT)
    assert plan.note is None


def test_the_built_binary_runs_next() -> None:
    plan = simulation(context())
    (simulate,) = (c.argv for c in plan.commands)
    assert simulate[0] == "./obj_dir/Vtb_top"
    assert f"+apx_seed={SEED}" in simulate
    assert "+apx_groups=public,hidden" in simulate
    assert "+verilator+rand+reset+2" in simulate
    assert f"+verilator+seed+{verilator_seed(SEED)}" in simulate
    nonce = next(a for a in simulate if a.startswith("+apx_nonce="))
    assert len(nonce) == len("+apx_nonce=") + 32
    assert not any(a.startswith("+apx_max_cycles") for a in simulate)
    assert plan.collect == ("tb_result.jsonl",)
    assert (plan.inputs, plan.note) == ({}, None)  # in the directory of the build


def test_build_and_run_share_the_stage_limits() -> None:
    ctx = context()
    plan = interpret(ctx, build=built(output="warning\n"))
    assert isinstance(plan, StagePlan)
    assert plan.timeout_s == ctx.limits.timeout_s - 3.0
    assert plan.output_limit == ctx.limits.output_bytes - len("warning\n")


def test_plan_options() -> None:
    ctx = context(["public"], max_cycles=500, design="synth.netlist_generic")
    build = SimStage().plan(ctx)
    simulate = simulation(ctx).commands[0].argv
    assert "+apx_max_cycles=500" in simulate
    assert "+apx_groups=public" in simulate
    assert build.inputs["design.v"] == b"module counter_net; endmodule\n"
    assert "solution.sv" not in build.inputs


def test_the_binary_is_cached_before_it_runs() -> None:
    cache = MemoryCache()
    ctx = context(cache=cache)
    key = cache_key(ctx)
    plan = SimStage().interpret(ctx, [built()])
    assert isinstance(plan, StagePlan)  # the run is only planned, the binary is already kept
    assert cache.files == {key: BINARY}


@pytest.mark.parametrize(
    "build",
    [built(binary=None), built(binary=None, oversized=frozenset({"obj_dir/Vtb_top"}))],
)
def test_a_binary_not_collected_still_runs_but_is_not_cached(build: ExecResult) -> None:
    cache = MemoryCache()
    assert isinstance(SimStage().interpret(context(cache=cache), [build]), StagePlan)
    assert cache.files == {}


def test_a_cached_binary_is_not_built_again() -> None:
    cache = MemoryCache()
    ctx = context(cache=cache)
    cache.put(cache_key(ctx), BINARY)
    plan = SimStage().plan(ctx)
    assert plan.commands[0].argv[0] == "./obj_dir/Vtb_top"
    assert plan.inputs == {"obj_dir/Vtb_top": BINARY}
    assert plan.executable == frozenset({"obj_dir/Vtb_top"})
    assert plan.note == CACHED_NOTE
    assert (plan.timeout_s, plan.output_limit) == (ctx.limits.timeout_s, ctx.limits.output_bytes)
    outcome = outcome_of(ctx, run_with(PASSED))
    assert (outcome.status, outcome.cached) == ("passed", True)
    assert not outcome_of(context(), run_with(PASSED)).cached


def test_a_cached_binary_records_the_trace_too() -> None:
    cache = MemoryCache()
    ctx = context(cache=cache)
    cache.put(cache_key(ctx), BINARY)
    assert isinstance(interpret(ctx, run_with(OPEN_FAIL)), StagePlan)
    outcome = outcome_of(ctx, run_with(OPEN_FAIL), run_with(OPEN_FAIL, trace=b"FST"))
    assert (outcome.cached, outcome.metrics["trace"]) == (True, "recorded")


def test_the_cache_key_is_what_the_build_reads() -> None:
    key = cache_key(context())
    # Run and Submit, any seed: the groups and the seed are arguments of the run, not the build.
    assert cache_key(context(["public"])) == key
    assert cache_key(context(max_cycles=10, trace=False)) == key
    assert cache_key(context(solution=b"module counter; wire a; endmodule\n")) != key
    assert cache_key(context(design="synth.netlist_generic")) != key
    assert cache_key(context(build_jobs=2)) != key


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"testbench": "other"}, "no testbench 'other'"),
        ({"design": "synth.netlist"}, "design synth.netlist was not produced"),
    ],
)
def test_plan_reports_missing_inputs(config: dict[str, Any], message: str) -> None:
    with pytest.raises(LookupError, match=message):
        SimStage().plan(context(**config))


@pytest.mark.parametrize("seed", [0, 1, 2**31 - 2, 2**31 - 1, 2**64 - 1])
def test_verilator_seed_is_a_positive_int(seed: int) -> None:
    assert 1 <= verilator_seed(seed) <= 2**31 - 1


def test_passed() -> None:
    outcome = outcome_of(context(), run_with(PASSED))
    assert outcome.status == "passed"
    assert outcome.metrics == {"tests_total": 3, "tests_passed": 3, "cycles": 63, "seed": SEED}
    assert [(t.id, t.status) for t in outcome.summary.tests] == [("t1", "passed"), ("t2", "passed")]
    hidden = outcome.summary.hidden_tests
    assert hidden is not None
    assert (hidden.total, hidden.passed, hidden.failed_index) == (1, 1, None)
    assert outcome.summary.caption == "пройдено 3 из 3"
    assert outcome.artifacts == {"tb_result.jsonl": PASSED}  # for the determinism check


def test_open_failure_asks_for_a_trace_window() -> None:
    plan = interpret(context(), run_with(OPEN_FAIL))
    assert isinstance(plan, StagePlan)
    argv = plan.commands[0].argv
    assert "+apx_trace_from=0" in argv  # max(0, 18 - 64)
    assert "+apx_trace_to=34" in argv
    assert "+apx_trace_file=trace.fst" in argv
    assert plan.collect == ("tb_result.jsonl", "trace.fst")
    assert plan.line_filter is not None
    assert plan.line_filter("anything") == (None, None)


def test_open_failure_with_recorded_trace() -> None:
    outcome = outcome_of(context(), run_with(OPEN_FAIL), run_with(OPEN_FAIL, trace=b"FST"))
    assert (outcome.status, outcome.failure_kind) == ("failed", "wrong")
    assert outcome.artifacts == {"tb_result.jsonl": OPEN_FAIL, "trace.fst": b"FST"}
    assert outcome.metrics["trace"] == "recorded"
    assert outcome.metrics["trace_window"] == [0, 34]
    assert outcome.metrics["trace_cursor_ps"] == 180_000
    assert [(s["path"], s["role"]) for s in outcome.metrics["trace_signals"]] == [
        ("tb_top.clk", "clock"),
        ("tb_top.rst", "input"),
        ("tb_top.en", "input"),
        ("tb_top.count", "output"),
        ("tb_top.exp_count", "expected"),
    ]
    assert outcome.metrics["first_failure"] == {"test": "t2", "cycle": 18, "signal": "count"}
    t2 = outcome.summary.tests[1]
    assert (t2.status, t2.cycle, t2.mismatches[0].hint) == ("failed", 18, "После 9 — 0")
    assert outcome.summary.caption == "упал тест тест t2, такт 18"


def test_trace_must_reproduce_the_mismatch() -> None:
    moved = OPEN_FAIL.replace(b'"cycle": 18', b'"cycle": 19')
    outcome = outcome_of(context(), run_with(OPEN_FAIL), run_with(moved, trace=b"FST"))
    assert outcome.metrics["trace"] == "nondeterministic"
    assert set(outcome.artifacts) == {"tb_result.jsonl"}  # no trace
    assert outcome.failure_kind == "wrong"  # the verdict of the first run stands


@pytest.mark.parametrize(
    ("trace_run", "status"),
    [
        (run_with(OPEN_FAIL, oversized=frozenset({"trace.fst"})), "too_large"),
        (run_with(OPEN_FAIL), "missing"),
        (run_with(None, timed_out=True), "failed"),
        (run_with(b"garbage\n"), "failed"),
    ],
)
def test_trace_problems_keep_the_verdict(trace_run: ExecResult, status: str) -> None:
    outcome = outcome_of(context(), run_with(OPEN_FAIL), trace_run)
    assert (outcome.failure_kind, outcome.metrics["trace"]) == ("wrong", status)
    assert set(outcome.artifacts) == {"tb_result.jsonl"}
    assert "trace_signals" not in outcome.metrics


def test_a_design_without_a_clock_port_is_traced_with_the_testbench_clock() -> None:
    problem = load_manifest(PACKAGE)
    ports = [p for p in problem.interface.ports if p.role != "clock"]
    combinational = problem.model_copy(
        update={"interface": problem.interface.model_copy(update={"ports": ports})}
    )
    signals = trace_signals(combinational, problem.testbenches[0])
    assert [(s.path, s.port, s.role) for s in signals][:2] == [
        ("tb_top.clk", "clk", "clock"),
        ("tb_top.rst", "rst", "input"),
    ]


def test_no_trace_when_disabled_or_for_a_netlist() -> None:
    for ctx in (context(trace=False), context(design="synth.netlist_generic")):
        outcome = outcome_of(ctx, run_with(OPEN_FAIL))
        assert "trace" not in outcome.metrics


def test_hidden_failure() -> None:
    outcome = outcome_of(context(), run_with(HIDDEN_FAIL))
    assert (outcome.status, outcome.failure_kind) == ("failed", "wrong")
    assert outcome.metrics["first_failure"] == {"test": "hidden-1", "cycle": 30, "signal": "count"}
    hidden = outcome.summary.hidden_tests
    assert hidden is not None
    assert (hidden.total, hidden.passed, hidden.failed_index) == (1, 0, 1)
    assert [t.id for t in outcome.summary.tests] == ["t1", "t2"]
    assert outcome.summary.caption == "упал скрытый тест 1, такт 30"


def test_group_counts_must_match_the_manifest() -> None:
    # counter declares public: 2, hidden: 1; this run has one public test.
    data = jsonl(
        START,
        started("t1", 0), ended("t1", "passed", 0, 7),
        started("h1", 7, "hidden"), ended("h1", "passed", 7, 40),
        rec("suite_end", passed=2, failed=0, not_run=0, cycles=40),
    )  # fmt: skip
    outcome = outcome_of(context(), run_with(data))
    assert (outcome.status, outcome.error_code) == ("error", "TB_GROUPS_MISMATCH")
    assert outcome.summary.caption == "в группе public тестов: 1, в problem.yaml: 2"


def test_skipped_tests_count_for_their_groups() -> None:
    # OPEN_FAIL skips h1 after t2 fails: the hidden group is still complete.
    assert outcome_of(context(trace=False), run_with(OPEN_FAIL)).failure_kind == "wrong"


def test_group_counts_are_not_checked_for_an_unfinished_run() -> None:
    data = jsonl(START, started("t1", 0), rec("suite_abort", reason="max_cycles", cycle=10_001))
    assert outcome_of(context(), run_with(data)).limit == "cycles"


def test_cycle_limit() -> None:
    data = jsonl(START, started("t1", 0), rec("suite_abort", reason="max_cycles", cycle=10_001))
    outcome = outcome_of(context(), run_with(data))
    assert (outcome.failure_kind, outcome.limit) == ("limit", "cycles")
    assert outcome.metrics["cycles"] == 10_001
    assert outcome.summary.tests[0].status == "running"


def test_simulation_died_without_a_summary() -> None:
    data = jsonl(START, started("t1", 0))
    outcome = outcome_of(context(), run_with(data, sim=139))
    assert (outcome.failure_kind, outcome.summary.caption) == (
        "wrong",
        "симуляция завершилась без итога тестбенча",
    )


@pytest.mark.parametrize(
    ("build", "detail"),
    [
        (built(None, binary=None, timed_out=True), "time"),
        (built(None, binary=None, output_limited=True), "output"),
        (built(137, binary=None), "memory"),
        (built(1, binary=None), "compile"),
    ],
)
def test_failed_builds(build: ExecResult, detail: str) -> None:
    outcome = SimStage().interpret(context(), [build])
    assert isinstance(outcome, StageOutcome)
    assert outcome.status == "failed"
    assert detail in (outcome.limit, outcome.failure_kind)


@pytest.mark.parametrize(
    ("run", "status", "detail"),
    [
        (run_with(None, None, timed_out=True), "failed", "time"),
        (run_with(None, None, output_limited=True), "failed", "output"),
        (run_with(jsonl(START, started("t1", 0)), sim=137), "failed", "memory"),
        (run_with(b"not json\n"), "error", "OUTPUT_INVALID"),
        (run_with(PASSED, oversized=frozenset({"tb_result.jsonl"})), "error", "OUTPUT_INVALID"),
        (run_with(jsonl(START, TB_ERROR)), "error", "TB_ERROR"),
    ],
)  # fmt: skip
def test_failed_runs(run: ExecResult, status: str, detail: str) -> None:
    outcome = outcome_of(context(), run)
    assert outcome.status == status
    assert detail in (outcome.limit, outcome.error_code, outcome.failure_kind)


def test_progress_lines_hide_hidden_tests() -> None:
    plan = simulation(context())
    nonce = next(a for a in plan.commands[0].argv if a.startswith("+apx_nonce="))[11:]
    line_filter = plan.line_filter
    assert line_filter is not None

    def progress(record: dict[str, Any]) -> tuple[str | None, Any]:
        return line_filter(f"@@apx:{nonce} " + json.dumps(record, ensure_ascii=False))

    shown, test = progress(started("t1", 0))
    assert shown is None
    assert (test.id, test.name, test.status) == ("t1", "тест t1", "running")
    _, test = progress(ended("t1", "passed", 0, 9))
    assert (test.id, test.name, test.group, test.status) == ("t1", "тест t1", "public", "passed")
    _, test = progress(started("h1", 9, "hidden"))
    assert (test.id, test.name, test.group) == ("hidden-1", "", "hidden")
    _, test = progress(ended("h1", "failed", 9, 20))
    assert (test.id, test.status) == ("hidden-1", "failed")
    assert progress(rec("suite_end", passed=1, failed=1, not_run=0, cycles=20)) == (None, None)
    assert line_filter("count=3") == ("count=3", None)
    assert line_filter("- /opt/apx/sv/apx_tb_pkg.sv:220: Verilog $finish") == (None, None)
    assert line_filter(f"@@apx:{'0' * 32} {{}}") == (f"@@apx:{'0' * 32} {{}}", None)
