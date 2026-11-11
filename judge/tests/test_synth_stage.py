"""The `synth` stage without the tools: its plan and its reading of what Yosys and OpenSTA wrote.

The files in data/synth/ are the real output of the stage plan in the toolchain image for counter
solutions: `good` synthesizes, `loop` has an incomplete always_comb, `latch` an incomplete
always @*, `drivers` two always_ff blocks driving one signal, `async` an edge on a data input
(an error of sv-elab).
"""

from pathlib import Path
from typing import Any

import pytest
from core_helpers import RESOURCE_CLASSES
from pydantic import ValidationError

from judge.core.limits import stage_limits
from judge.core.package import Parameter, Port, Problem, load_manifest
from judge.core.stage import (
    CommandResult,
    ExecResult,
    FinishedStage,
    StageContext,
    StageOutcome,
    StageResult,
)
from judge.languages.systemverilog.stages.synth import (
    CHECK,
    LATCH_SOURCES,
    NANGATE45,
    NETLIST_GENERIC,
    STA_RESULT,
    STA_SCRIPT,
    STAT,
    YOSYS_SCRIPT,
    SynthConfig,
    SynthStage,
    console_line,
    synth_params,
)

DATA = Path(__file__).parent / "data"
PACKAGE = DATA / "packages" / "counter"
CANONICAL = b"module counter; endmodule\n"
YOSYS = ("yosys", "-qq", "-w", ".*", "-s", YOSYS_SCRIPT)
STA = ("sta", "-no_init", "-no_splash", "-exit", STA_SCRIPT)


def problem(**interface: Any) -> Problem:
    loaded = load_manifest(PACKAGE)
    if not interface:
        return loaded
    return loaded.model_copy(update={"interface": loaded.interface.model_copy(update=interface)})


def context(target: Problem | None = None, **config: Any) -> StageContext:
    target = target or problem()
    previous = {
        "precheck": FinishedStage(
            StageResult(key="precheck", type="precheck", ordinal=0, status="passed"),
            {"solution.sv": CANONICAL},
        )
    }
    return StageContext(
        key="synth",
        type="synth",
        ordinal=1,
        config=SynthConfig.model_validate(config),
        problem=target,
        package_dir=PACKAGE,
        kind="submit",
        seed=1,
        solution=b"// original\n",
        limits=stage_limits(target, "synth", "synth", RESOURCE_CLASSES),
        previous=previous,
    )


def fixture(case: str) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in (DATA / "synth" / case).iterdir()}


def run(
    files: dict[str, bytes],
    *,
    yosys: int | None = 0,
    sta: int | None = 0,
    output: str = "",
    **flags: Any,
) -> ExecResult:
    commands = [CommandResult(YOSYS, yosys, 1.0)]
    if yosys == 0:
        commands.append(CommandResult(STA, sta, 0.3))
    return ExecResult(commands=tuple(commands), output=output, files=files, **flags)


def interpret(execution: ExecResult, ctx: StageContext | None = None) -> StageOutcome:
    ctx = ctx or context()
    outcome = SynthStage().interpret(ctx, [execution])
    assert isinstance(outcome, StageOutcome)
    return outcome


# --- plan ----------------------------------------------------------------------------------------


def test_the_plan_runs_yosys_then_opensta_on_the_canonical_text() -> None:
    plan = SynthStage().plan(context())
    assert [command.argv for command in plan.commands] == [YOSYS, STA]
    assert plan.inputs["solution.sv"] == CANONICAL
    assert plan.cache, "synthesis is deterministic: the pipeline keeps it in the stage cache"
    assert NETLIST_GENERIC in plan.collect


def test_the_yosys_script_reads_the_code_as_simulation_does() -> None:
    script = SynthStage().plan(context()).inputs[YOSYS_SCRIPT].decode()
    lines = script.splitlines()
    assert lines[0] == f"read_liberty -lib {NANGATE45.path}"
    assert lines[1] == (
        "read_slang --no-synthesis-define --no-default-translate-off-format solution.sv"
        " --top counter"
    )
    # Drivers are checked before synth resolves conflicts with constants, loops after it.
    assert lines.index("tee -q -o check_rtl.txt check") < lines.index("synth -top counter -flatten")
    assert lines.index("synth -top counter -flatten") < lines.index("tee -q -o check.txt check")
    assert "rename counter counter__netlist" in lines
    assert "tee -q -o ltp.txt ltp -noff * t:DFF* t:SDFF* %u %d" in lines
    assert lines[-1] == "write_verilog -noexpr -noattr netlist.v"


def test_parameters_take_the_values_of_the_primary_set() -> None:
    parameters = [
        Parameter(name="WIDTH", type="int", default=8),
        Parameter(name="DEPTH", type="int", default=16),
        Parameter(name="INIT", type="logic", default="4'hA"),
    ]
    target = problem(parameters=parameters)
    assert synth_params(target) == {"WIDTH": "8", "DEPTH": "16", "INIT": "4'hA"}
    script = SynthStage().plan(context(target)).inputs[YOSYS_SCRIPT].decode()
    assert "--top counter -G WIDTH=8 -G DEPTH=16 -G INIT=4'hA\n" in script


def test_a_default_must_be_a_literal() -> None:
    target = problem(parameters=[Parameter(name="W", type="int", default="8; shell rm")])
    with pytest.raises(ValueError, match="not a literal"):
        synth_params(target)


def test_the_stage_takes_no_parameter_values() -> None:
    with pytest.raises(ValidationError, match="params"):
        SynthConfig.model_validate({"params": {"WIDTH": 4}})


def test_opensta_constraints_are_fixed_and_clock_the_clock_port() -> None:
    script = SynthStage().plan(context(clock_period_ns=1.5)).inputs[STA_SCRIPT].decode()
    assert "create_clock -name clk -period 1.5 [get_ports {clk}]" in script
    assert "set data_inputs [delete_from_list [all_inputs] [get_ports {clk}]]" in script
    assert "set_driving_cell -lib_cell BUF_X1 $data_inputs" in script
    assert "get_lib_pins NangateOpenCellLibrary/DFF_X1/D" in script
    assert f"set result [open {STA_RESULT} w]" in script


def test_a_design_without_a_clock_port_gets_a_virtual_clock() -> None:
    ports = [
        Port(name="a", dir="input", width="4"),
        Port(name="y", dir="output", width="4"),
    ]
    script = SynthStage().plan(context(problem(ports=ports))).inputs[STA_SCRIPT].decode()
    assert "create_clock -name clk -period 2.0\n" in script
    assert "set data_inputs [all_inputs]" in script


def test_two_clock_ports_are_a_problem_error() -> None:
    ports = [*problem().interface.ports, Port(name="clk2", dir="input", width="1", role="clock")]
    with pytest.raises(ValueError, match="one clock"):
        SynthStage().plan(context(problem(ports=ports)))


# --- interpretation ------------------------------------------------------------------------------


def test_a_synthesized_design_has_its_metrics_and_the_netlist_for_netlist_sim() -> None:
    files = fixture("good")
    outcome = interpret(run(files))
    assert outcome.status == "passed"
    assert outcome.metrics == {
        "critical_path_ns": 0.246,
        "fmax_mhz": 4065.04,
        "area_um2": 36.18,
        "cells": 23,
        "flops": 4,
        "latches": 0,
        "logic_depth": 3,
        "liberty": "nangate45",
        "cells_by_type": {
            "AND3_X1": 1,
            "AOI21_X1": 3,
            "DFF_X1": 4,
            "INV_X1": 5,
            "NAND2_X1": 2,
            "NAND3_X1": 2,
            "OAI211_X1": 2,
            "OAI21_X1": 3,
            "OAI22_X1": 1,
        },
    }
    assert outcome.outputs == {"netlist_generic": files[NETLIST_GENERIC]}
    assert outcome.summary.caption == "0,246 нс, 36,18 мкм², ячеек 23"


def test_a_combinational_design_has_a_delay_but_no_frequency() -> None:
    ports = [Port(name="a", dir="input", width="4"), Port(name="y", dir="output", width="4")]
    outcome = interpret(run(fixture("good")), context(problem(ports=ports)))
    assert outcome.metrics["critical_path_ns"] == 0.246
    assert "fmax_mhz" not in outcome.metrics


def test_a_design_without_timing_paths_has_zero_delay() -> None:
    files = fixture("good") | {STA_RESULT: b'{"wns_ns": 1000000043329398871556523614962693.0}'}
    outcome = interpret(run(files))
    assert outcome.status == "passed"
    assert outcome.metrics["critical_path_ns"] == 0
    assert "fmax_mhz" not in outcome.metrics


def test_an_empty_design_has_zero_area() -> None:
    stat = b'{"design": {"num_cells": 0, "num_cells_by_type": {}}}'
    outcome = interpret(run(fixture("good") | {STAT: stat}))
    assert (outcome.metrics["area_um2"], outcome.metrics["cells"]) == (0, 0)


def test_latches_fail_as_compile_at_the_block_that_infers_them() -> None:
    outcome = interpret(run(fixture("latch")))
    assert (outcome.status, outcome.failure_kind) == ("failed", "compile")
    assert outcome.summary.caption == "латчи в схеме"
    [diagnostic] = outcome.summary.diagnostics
    assert (diagnostic.code, diagnostic.file, diagnostic.line, diagnostic.col) == (
        "LATCH",
        "solution.sv",
        4,
        3,
    )
    assert not outcome.outputs


def test_latches_without_their_places_still_fail() -> None:
    files = fixture("latch")
    del files[LATCH_SOURCES]
    [diagnostic] = interpret(run(files)).summary.diagnostics
    assert (diagnostic.code, diagnostic.line, diagnostic.message) == (
        "LATCH",
        None,
        "латчей в схеме: 4",
    )


def test_latches_pass_when_the_problem_allows_them() -> None:
    outcome = interpret(run(fixture("latch")), context(forbid_latches=False))
    assert outcome.status == "passed"
    assert outcome.metrics["latches"] == 4


def test_a_loop_of_an_incomplete_always_comb_fails_as_compile() -> None:
    outcome = interpret(run(fixture("loop")))
    assert (outcome.status, outcome.failure_kind) == ("failed", "compile")
    assert outcome.summary.caption == "комбинационная петля"
    [diagnostic] = outcome.summary.diagnostics  # one per signal, not per looped bit
    assert (diagnostic.code, diagnostic.line, diagnostic.col) == ("LOGIC_LOOP", 3, 15)
    assert "сигнал next" in diagnostic.message


def test_a_loop_is_allowed_with_latches() -> None:
    outcome = interpret(run(fixture("loop")), context(forbid_latches=False))
    assert outcome.status == "passed"


def test_conflicting_drivers_fail_as_compile() -> None:
    outcome = interpret(run(fixture("drivers")), context(forbid_latches=False))
    assert (outcome.status, outcome.failure_kind) == ("failed", "compile")
    [diagnostic] = outcome.summary.diagnostics
    assert (diagnostic.code, diagnostic.message) == (
        "MULTIPLE_DRIVERS",
        "у сигнала count несколько драйверов: синтез не может их объединить",
    )


def test_a_yosys_error_is_compile_with_the_line_of_the_solution() -> None:
    console = (DATA / "synth" / "async" / "console.txt").read_text(encoding="utf-8")
    outcome = interpret(run({}, yosys=1, output=console))
    assert (outcome.status, outcome.failure_kind) == ("failed", "compile")
    assert outcome.summary.caption == "решение не синтезируется"
    [diagnostic] = outcome.summary.diagnostics  # the generic "elaboration failed" is dropped
    assert (diagnostic.code, diagnostic.file, diagnostic.line) == ("SYNTH_ERROR", "solution.sv", 4)
    assert diagnostic.message == (
        "simple if-else pattern expected in modeling an asynchronous load on a flip-flop"
    )


def test_the_console_loses_the_colors_and_the_missing_log() -> None:
    line = (
        "\x1b[0m\x1b[91mERROR: \x1b[0m\x1b[1m\x1b[34m"
        "Design elaboration failed; see full log for details"
    )
    assert console_line(line) == ("ERROR: Design elaboration failed", None)


@pytest.mark.parametrize(
    ("execution", "expected"),
    [
        pytest.param(run({}, yosys=None, timed_out=True), ("limit", "time", None), id="timeout"),
        pytest.param(
            run({}, yosys=None, output_limited=True), ("limit", "output", None), id="output"
        ),
        pytest.param(run({}, yosys=137), ("limit", "memory", None), id="yosys-memory"),
        pytest.param(
            run({}, yosys=134, output="Segmentation fault"),
            (None, None, "TOOL_FAILED"),
            id="yosys-crash",
        ),
        pytest.param(run(fixture("good"), sta=1), (None, None, "TOOL_FAILED"), id="sta-failed"),
        pytest.param(run(fixture("good"), sta=137), ("limit", "memory", None), id="sta-memory"),
        pytest.param(
            run(fixture("good") | {STAT: b'{"design": {"num_cells": "many"}}'}),
            (None, None, "OUTPUT_INVALID"),
            id="stat-not-a-number",
        ),
        pytest.param(
            run(fixture("good") | {STA_RESULT: b"forged"}),
            (None, None, "OUTPUT_INVALID"),
            id="sta-result-forged",
        ),
        pytest.param(
            run({k: v for k, v in fixture("good").items() if k != NETLIST_GENERIC}),
            (None, None, "OUTPUT_INVALID"),
            id="no-netlist",
        ),
        pytest.param(
            run(fixture("good") | {CHECK: b"nothing"}),
            (None, None, "OUTPUT_INVALID"),
            id="check-without-summary",
        ),
        pytest.param(
            run({**fixture("good"), STA_RESULT: b'{"wns_ns": 5.0}'}),
            (None, None, "OUTPUT_INVALID"),
            id="slack-over-the-period",
        ),
        pytest.param(
            run(fixture("good"), oversized=frozenset({NETLIST_GENERIC})),
            ("limit", "output", None),
            id="netlist-too-large",
        ),
        pytest.param(
            run(fixture("good"), oversized=frozenset({STAT})),
            (None, None, "OUTPUT_INVALID"),
            id="stat-too-large",
        ),
    ],
)
def test_untrusted_output_and_limits(
    execution: ExecResult, expected: tuple[str | None, str | None, str | None]
) -> None:
    outcome = interpret(execution)
    assert (outcome.failure_kind, outcome.limit, outcome.error_code) == expected


def test_too_many_check_problems_are_compile() -> None:
    outcome = interpret(run(fixture("good"), oversized=frozenset({CHECK})))
    assert (outcome.status, outcome.failure_kind) == ("failed", "compile")
    assert [d.code for d in outcome.summary.diagnostics] == ["SYNTH_CHECK"]
