"""`sim` stage (specs/07 §2.3, FR-JDG-04/05): build the testbench with Verilator and simulate.

One plan builds `apx_tb_pkg` + the problem testbench + the design with `apx-verilate` and runs the
binary with the submission seed, the selected groups and random initialization. The verdict comes
from the result file of `apx_tb_pkg` (untrusted, `tbproto`); progress lines become live test
events. When an open test fails, a follow-up run of the same binary records the FST trace window
around the first mismatch and must reproduce that mismatch (ADR-0004).
"""

import re
from collections.abc import Sequence
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, StringConstraints

from judge.core.executor import check_relative
from judge.core.package import Testbench
from judge.core.stage import (
    Command,
    ExecResult,
    HiddenTests,
    Mismatch,
    StageContext,
    StageOutcome,
    StagePlan,
    StageSummary,
    TestCase,
)
from judge.languages.systemverilog import tbproto
from judge.languages.systemverilog.stages.common import SOLUTION, canonical_solution

TB_PKG = "/opt/apx/sv/apx_tb_pkg.sv"
RESULT = "tb_result.jsonl"
TRACE = "trace.fst"
RESULT_LIMIT = 1 << 20
OPEN_GROUP = "public"  # tests of other groups are hidden: counters only (specs/06 §3.4)
OOM_KILLED = 137
# The `$finish` notice of apx_tb_pkg names an internal file: not for the user's console.
_FINISH_NOTICE = re.compile(r"^- \S*apx_tb_pkg\.sv:\d+: Verilog \$finish$")

DesignRef = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]+\.[A-Za-z0-9_.-]+$")]


class SimConfig(BaseModel):
    """`stages.<key>` of type sim (specs/06 §2)."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    testbench: str
    groups: Annotated[list[str], Field(min_length=1)]
    max_cycles: PositiveInt | None = None
    design: DesignRef | None = Field(
        default=None,
        description="<stage>.<output> to simulate instead of the solution, e.g. a netlist",
    )
    trace: bool = True
    trace_before: NonNegativeInt = 64
    trace_after: PositiveInt = 16
    build_jobs: PositiveInt = 1  # S2: parallel builds do not pay off with the prebuilt runtime


class FirstFailure(BaseModel):
    test: str
    cycle: int
    signal: str


class SimMetrics(BaseModel):
    """`sim/v1` (specs/04 §5)."""

    tests_total: int
    tests_passed: int
    cycles: int
    seed: int
    first_failure: FirstFailure | None = None
    trace: Literal["recorded", "too_large", "missing", "nondeterministic", "failed"] | None = None
    trace_window: tuple[int, int] | None = None


def verilator_seed(seed: int) -> int:
    """+verilator+seed takes a positive int; 0 would mean a random seed."""
    return seed % (2**31 - 1) + 1


def _testbench(ctx: StageContext, config: SimConfig) -> Testbench:
    for testbench in ctx.problem.testbenches:
        if testbench.id == config.testbench:
            return testbench
    raise LookupError(f"stage {ctx.key}: no testbench {config.testbench!r} in problem.yaml")


def _package_file(ctx: StageContext, name: str) -> bytes:
    root = ctx.package_dir.resolve()
    path = (root / check_relative(name)).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"testbench source {name!r} is outside the package")
    return path.read_bytes()


def _design(ctx: StageContext, config: SimConfig) -> tuple[str, bytes]:
    if config.design is None:
        return SOLUTION, canonical_solution(ctx)
    stage, output = config.design.split(".", 1)
    finished = ctx.previous.get(stage)
    if finished is None or output not in finished.outputs:
        raise LookupError(f"stage {ctx.key}: design {config.design} was not produced")
    return "design.v", finished.outputs[output]


class _Progress:
    """Turns progress lines of apx_tb_pkg into test events; hidden tests stay anonymous.

    Every event of a test is complete: the end record has no name and group, so they come from
    the start record (the client replaces a test by id)."""

    def __init__(self, nonce: str) -> None:
        self.nonce = nonce
        self.hidden: dict[str, str] = {}
        self.started: dict[str, tuple[str, str]] = {}

    def __call__(self, line: str) -> tuple[str | None, TestCase | None]:
        text, record = tbproto.split_progress(line, self.nonce)
        shown = None if _FINISH_NOTICE.match(text) or (record and not text) else text
        match record:
            case tbproto.TestStart():
                self.started[record.id] = (record.name, record.group)
                return shown, self._case(record.id, record.name, record.group, "running")
            case tbproto.TestEnd():
                name, group = self.started.get(record.id, ("", ""))
                return shown, self._case(record.id, name, group, record.status)
            case tbproto.TestSkip():
                return shown, self._case(record.id, record.name, record.group, "not_run")
        return shown, None

    def _case(
        self,
        test_id: str,
        name: str,
        group: str,
        status: Literal["passed", "failed", "running", "not_run"],
    ) -> TestCase:
        if test_id in self.hidden or (group and group != OPEN_GROUP):
            alias = self.hidden.setdefault(test_id, f"hidden-{len(self.hidden) + 1}")
            return TestCase(id=alias, name="", group="hidden", status=status)
        return TestCase(id=test_id, name=name, group=group or OPEN_GROUP, status=status)


def _hide_all(line: str) -> tuple[str | None, TestCase | None]:
    return None, None


class SimStage:
    stage_type: ClassVar[str] = "sim"
    config_model: ClassVar[type[BaseModel]] = SimConfig
    metrics_schema: ClassVar[str | None] = "sim/v1"

    def plan(self, ctx: StageContext) -> StagePlan:
        assert isinstance(ctx.config, SimConfig)
        config = ctx.config
        testbench = _testbench(ctx, config)
        sources = {f"pkg/{name}": _package_file(ctx, name) for name in testbench.sources}
        design_name, design = _design(ctx, config)
        build = (
            "apx-verilate",
            "--quiet",
            "-MAKEFLAGS",
            "-s",
            "--timescale",
            "1ps/1ps",
            "--x-assign",
            "unique",
            "--x-initial",
            "unique",
            "-j",
            str(config.build_jobs),
            "-Wno-fatal",
            "-Wno-lint",
            TB_PKG,
            *sources,
            design_name,
            "--top-module",
            testbench.top,
        )
        nonce = tbproto.new_nonce()
        return StagePlan(
            commands=(Command(build), Command(self._run_argv(ctx, testbench, nonce))),
            timeout_s=ctx.limits.timeout_s,
            output_limit=ctx.limits.output_bytes,
            inputs={**sources, design_name: design},
            collect=(RESULT,),
            collect_limit=RESULT_LIMIT,
            line_filter=_Progress(nonce),
        )

    def _run_argv(
        self, ctx: StageContext, testbench: Testbench, nonce: str, *extra: str
    ) -> tuple[str, ...]:
        assert isinstance(ctx.config, SimConfig)
        cycles = (
            () if ctx.config.max_cycles is None else (f"+apx_max_cycles={ctx.config.max_cycles}",)
        )
        return (
            f"./obj_dir/V{testbench.top}",
            f"+apx_seed={ctx.seed}",
            f"+apx_groups={','.join(ctx.config.groups)}",
            f"+apx_result={RESULT}",
            f"+apx_nonce={nonce}",
            *cycles,
            *extra,
            f"+verilator+seed+{verilator_seed(ctx.seed)}",
            "+verilator+rand+reset+2",
            "+verilator+quiet",
        )

    def interpret(self, ctx: StageContext, runs: Sequence[ExecResult]) -> StageOutcome | StagePlan:
        assert isinstance(ctx.config, SimConfig)
        outcome, result = self._outcome(ctx, runs[0])
        if RESULT in runs[0].files:
            # Kept for the determinism check and for authors; it holds hidden test values, so it
            # is never shown to users of a run with hidden groups (specs/07 §4.4).
            outcome = outcome.model_copy(update={"artifacts": {RESULT: runs[0].files[RESULT]}})
        window = self._trace_window(ctx, outcome, result)
        if window is None:
            return outcome
        if len(runs) == 1:
            start, stop = window
            argv = self._run_argv(
                ctx,
                _testbench(ctx, ctx.config),
                tbproto.new_nonce(),
                f"+apx_trace_from={start}",
                f"+apx_trace_to={stop}",
                f"+apx_trace_file={TRACE}",
            )
            return StagePlan(
                commands=(Command(argv),),
                timeout_s=ctx.limits.timeout_s,
                output_limit=ctx.limits.output_bytes,
                collect=(RESULT, TRACE),
                collect_limit=max(RESULT_LIMIT, ctx.limits.fst_bytes),
                line_filter=_hide_all,  # the console already has this run
            )
        return self._with_trace(outcome, result, runs[1], window)

    def _outcome(
        self, ctx: StageContext, run: ExecResult
    ) -> tuple[StageOutcome, tbproto.TbResult | None]:
        if run.timed_out:
            return StageOutcome(status="failed", failure_kind="limit", limit="time"), None
        if run.output_limited:
            return StageOutcome(status="failed", failure_kind="limit", limit="output"), None
        build = run.commands[0]
        if build.exit_code == OOM_KILLED:
            return StageOutcome(status="failed", failure_kind="limit", limit="memory"), None
        if build.exit_code != 0:
            summary = StageSummary(caption="решение не собирается вместе с тестбенчем")
            return StageOutcome(status="failed", failure_kind="compile", summary=summary), None
        if len(run.commands) < 2 or RESULT in run.oversized:
            return StageOutcome(status="error", error_code="OUTPUT_INVALID"), None
        try:
            result = tbproto.parse_result(run.files.get(RESULT, b""), max_bytes=RESULT_LIMIT)
        except tbproto.ProtocolError:
            return StageOutcome(status="error", error_code="OUTPUT_INVALID"), None
        if result.abort is not None and result.abort.reason == "tb_error":
            return StageOutcome(status="error", error_code="TB_ERROR"), result
        mismatch = _group_count_mismatch(ctx, result)
        if mismatch is not None:
            summary = StageSummary(caption=mismatch)
            return StageOutcome(
                status="error", error_code="TB_GROUPS_MISMATCH", summary=summary
            ), result
        summary, metrics = self._report(ctx, result)
        failed = any(test.status == "failed" for test in result.tests)
        if failed:
            outcome = StageOutcome(
                status="failed", failure_kind="wrong", metrics=metrics, summary=summary
            )
        elif result.abort is not None:  # the cycle limit
            outcome = StageOutcome(
                status="failed",
                failure_kind="limit",
                limit="cycles",
                metrics=metrics,
                summary=summary,
            )
        elif result.end is None:
            if run.commands[1].exit_code == OOM_KILLED:
                outcome = StageOutcome(
                    status="failed",
                    failure_kind="limit",
                    limit="memory",
                    metrics=metrics,
                    summary=summary,
                )
            else:  # the simulation died before the end of the suite (specs/06 §3.3)
                caption = "симуляция завершилась без итога тестбенча"
                outcome = StageOutcome(
                    status="failed",
                    failure_kind="wrong",
                    metrics=metrics,
                    summary=summary.model_copy(update={"caption": caption}),
                )
        else:
            outcome = StageOutcome(status="passed", metrics=metrics, summary=summary)
        return outcome, result

    def _report(
        self, ctx: StageContext, result: tbproto.TbResult
    ) -> tuple[StageSummary, dict[str, object]]:
        assert isinstance(ctx.config, SimConfig)
        groups = _testbench(ctx, ctx.config).groups
        open_tests = [t for t in result.tests if t.group == OPEN_GROUP]
        hidden = [t for t in result.tests if t.group != OPEN_GROUP]
        hidden_groups = [g for g in ctx.config.groups if g != OPEN_GROUP]
        hidden_tests = None
        if hidden_groups:
            failed_index = next(
                (i for i, t in enumerate(hidden, start=1) if t.status == "failed"), None
            )
            hidden_tests = HiddenTests(
                total=sum(groups.get(g, 0) for g in hidden_groups) or len(hidden),
                passed=sum(t.status == "passed" for t in hidden),
                failed_index=failed_index,
            )
        total = sum(groups.get(g, 0) for g in ctx.config.groups) or len(result.tests)
        passed = sum(t.status == "passed" for t in result.tests)
        first = result.first_mismatch
        failure = None
        caption = f"пройдено {passed} из {total}"
        if first is not None:
            failed_test = next(t for t in result.tests if t.id == first.test)
            name = first.test
            if failed_test.group != OPEN_GROUP:
                name = f"hidden-{hidden.index(failed_test) + 1}"
                caption = f"упал скрытый тест {hidden.index(failed_test) + 1}, такт {first.cycle}"
            else:
                caption = f"упал тест {failed_test.name or first.test}, такт {first.cycle}"
            failure = FirstFailure(test=name, cycle=first.cycle, signal=first.signal)
        cycles = (
            result.end.cycles
            if result.end
            else result.abort.cycle
            if result.abort
            else max((t.end_cycle or t.start_cycle or 0 for t in result.tests), default=0)
        )
        metrics = SimMetrics(
            tests_total=total,
            tests_passed=passed,
            cycles=cycles,
            seed=ctx.seed,
            first_failure=failure,
        )
        summary = StageSummary(
            caption=caption,
            tests=[_test_case(t) for t in open_tests],
            hidden_tests=hidden_tests,
        )
        return summary, metrics.model_dump(exclude_none=True)

    def _trace_window(
        self, ctx: StageContext, outcome: StageOutcome, result: tbproto.TbResult | None
    ) -> tuple[int, int] | None:
        """The window around the first mismatch of an open test, if a trace is due."""
        assert isinstance(ctx.config, SimConfig)
        config = ctx.config
        if not config.trace or config.design is not None or outcome.failure_kind != "wrong":
            return None
        first = result.first_mismatch if result else None
        if first is None or result is None:
            return None
        failed = next(t for t in result.tests if t.id == first.test)
        if failed.group != OPEN_GROUP:
            return None  # hidden tests are never traced
        return max(0, first.cycle - config.trace_before), first.cycle + config.trace_after

    def _with_trace(
        self,
        outcome: StageOutcome,
        result: tbproto.TbResult | None,
        trace_run: ExecResult,
        window: tuple[int, int],
    ) -> StageOutcome:
        status: Literal["recorded", "too_large", "missing", "nondeterministic", "failed"]
        artifacts = dict(outcome.artifacts)
        try:
            traced = tbproto.parse_result(trace_run.files.get(RESULT, b""), max_bytes=RESULT_LIMIT)
        except tbproto.ProtocolError:
            traced = None
        if trace_run.timed_out or trace_run.output_limited or traced is None:
            status = "failed"
        elif result is None or _key(traced.first_mismatch) != _key(result.first_mismatch):
            # The same binary and seed must fail at the same cycle: a problem bug, not shown.
            status = "nondeterministic"
        elif TRACE in trace_run.oversized:
            status = "too_large"
        elif TRACE not in trace_run.files:
            status = "missing"
        else:
            status = "recorded"
            artifacts[TRACE] = trace_run.files[TRACE]
        metrics = {**outcome.metrics, "trace": status}
        if status == "recorded":
            metrics["trace_window"] = list(window)
        return outcome.model_copy(update={"metrics": metrics, "artifacts": artifacts})


def _group_count_mismatch(ctx: StageContext, result: tbproto.TbResult) -> str | None:
    """A finished suite lists every test of the selected groups (failed, passed or skipped): their
    numbers must match testbenches[].groups. A mismatch is a problem bug (FR-PKG-03), caught by
    `judge validate` on the reference solutions."""
    assert isinstance(ctx.config, SimConfig)
    if result.end is None:
        return None
    declared = _testbench(ctx, ctx.config).groups
    for group in ctx.config.groups:
        actual = sum(test.group == group for test in result.tests)
        expected = declared.get(group)
        if actual != expected:
            in_manifest = "группа не объявлена" if expected is None else str(expected)
            return f"в группе {group} тестов: {actual}, в problem.yaml: {in_manifest}"
    return None


def _key(mismatch: tbproto.Mismatch | None) -> tuple[str, int, str] | None:
    return None if mismatch is None else (mismatch.test, mismatch.cycle, mismatch.signal)


def _test_case(test: tbproto.TestCase) -> TestCase:
    first = test.mismatches[0] if test.mismatches else None
    return TestCase(
        id=test.id,
        name=test.name,
        group=test.group,
        status=test.status,
        cycle=first.cycle if first else None,
        mismatches=[
            Mismatch(
                signal=m.signal, cycle=m.cycle, expected=m.expected, actual=m.actual, hint=m.hint
            )
            for m in test.mismatches
        ],
    )
