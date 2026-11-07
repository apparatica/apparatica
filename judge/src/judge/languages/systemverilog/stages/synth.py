"""`synth` stage (specs/07 §2.4, FR-SYN-01/02, ADR-0007): Yosys with sv-elab, then OpenSTA.

One plan of two commands on the canonical text: Yosys reads it with `read_slang` (no implicit
`SYNTHESIS` define, `translate_off` comments are plain comments), synthesizes, writes the netlist on
its internal gates for `netlist_sim`, maps to the Nangate45 liberty and measures area, cells and
logic depth; OpenSTA times the mapped netlist under constraints fixed here, not taken from the
solution. Latches and combinational loops (an incomplete `always @*` or `always_comb`) and signals
with several drivers fail the stage as `compile`, like code sv-elab cannot synthesize. Yosys colors
its messages under the TTY of the stage: the colors are removed before the console and parsing.

Everything the tools write is untrusted: every file has a size bound and a strict format. The run is
deterministic (S4), so the pipeline keeps it in the stage cache by its plan: the canonical text, the
parameters and the scripts (FR-JDG-11).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Annotated, ClassVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveFloat,
    StringConstraints,
    ValidationError,
)

from judge.core.package import Identifier, Problem
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


@dataclass(frozen=True)
class Liberty:
    """The synthesis library of the toolchain image and the fixed constraints taken from it."""

    name: str  # `liberty` of the metrics; versions.lock has `<NAME>_LIB_SHA256` for it
    path: str
    library: str  # the `library` group of the file
    tie_high: str  # cell and pin of a constant 1
    tie_low: str
    driving_cell: str  # drives every data input
    load_pin: str  # every output drives the capacitance of this pin
    flops: tuple[str, ...]  # name patterns of exactly the cells with an `ff` group


NANGATE45 = Liberty(
    name="nangate45",
    path="/opt/pdk/nangate45/NangateOpenCellLibrary_typical.lib",
    library="NangateOpenCellLibrary",
    tie_high="LOGIC1_X1 Z",
    tie_low="LOGIC0_X1 Z",
    driving_cell="BUF_X1",
    load_pin="DFF_X1/D",
    flops=("DFF*", "SDFF*"),
)

YOSYS_SCRIPT = "synth.ys"
STA_SCRIPT = "sta.tcl"
NETLIST_GENERIC = "netlist_generic.v"  # Yosys internal gates: the design of netlist_sim
NETLIST = "netlist.v"  # liberty cells: what OpenSTA times
LATCHES = "latches.txt"
LATCH_SOURCES = "latch_sources.txt"
CHECK_RTL = "check_rtl.txt"  # before synth: `synth` resolves conflicting drivers with constants
CHECK = "check.txt"  # after synth: loops through gates, not through word-level cells
STAT = "stat.json"
LTP = "ltp.txt"
STA_RESULT = "sta.json"
FILE_LIMIT = 16 << 20
OOM_KILLED = 137
# What sv-elab and `synth` leave for a latch: Yosys latch and set-reset cells (S4).
LATCH_CELLS = "t:$_DLATCH* t:$_DLATCHSR* t:$_SR_* t:$dlatch* t:$sr"
# Slack of a design without timing paths (OpenSTA reports a huge number).
NO_PATHS_SLACK = 1e30
# The precision of the tools (ADR-0006): finer digits would tell apart solutions the leaderboard
# should rank together. Delay in ns to 1 ps, area in µm² to 0.01.
DELAY_DIGITS = 3
AREA_DIGITS = 2
MAX_DIAGNOSTICS = 50

# A parameter value goes into the Yosys script: a number literal only, no spaces or separators.
LITERAL = r"^-?[0-9][0-9_]*$|^[0-9]*'[sS]?[bBoOdDhH][0-9a-fA-FxXzZ?_]+$"
ParamValue = int | Annotated[str, StringConstraints(pattern=LITERAL)]


class SynthConfig(BaseModel):
    """`stages.<key>` of type synth (specs/06 §2)."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    params: dict[Identifier, ParamValue] = Field(
        default={},
        description="Parameter values to synthesize with; the others keep the problem defaults",
    )
    clock_period_ns: PositiveFloat = 2.0
    forbid_latches: bool = True


class SynthMetrics(BaseModel):
    """`synth/v1` (specs/04 §5)."""

    critical_path_ns: float = Field(description="Clock period minus the worst slack; 0: no paths")
    fmax_mhz: float | None = Field(default=None, description="Only for a design with a clock")
    area_um2: float
    cells: NonNegativeInt
    flops: NonNegativeInt
    latches: NonNegativeInt
    logic_depth: NonNegativeInt
    liberty: str
    cells_by_type: dict[str, NonNegativeInt]


def synth_params(problem: Problem, config: SynthConfig) -> dict[str, str]:
    """Every parameter of the interface with the value the design is synthesized with."""
    declared = {parameter.name: parameter.default for parameter in problem.interface.parameters}
    unknown = sorted(set(config.params) - set(declared))
    if unknown:
        raise ValueError(f"synth params not in interface.parameters: {', '.join(unknown)}")
    values = {name: str(config.params.get(name, default)) for name, default in declared.items()}
    for name, value in values.items():
        if not re.match(LITERAL, value):
            raise ValueError(f"parameter {name}: {value!r} is not a literal")
    return values


def clock_port(problem: Problem) -> str | None:
    clocks = [port.name for port in problem.interface.ports if port.role == "clock"]
    if len(clocks) > 1:
        raise ValueError(f"synth times one clock, the interface has {', '.join(clocks)}")
    return clocks[0] if clocks else None


def yosys_script(top: str, params: dict[str, str], liberty: Liberty = NANGATE45) -> str:
    lib = liberty.path
    overrides = "".join(f" -G {name}={value}" for name, value in params.items())
    flops = " ".join(f"t:{pattern}" for pattern in liberty.flops)
    flops += " %u" * (len(liberty.flops) - 1)
    return "\n".join(
        [
            f"read_liberty -lib {lib}",
            "read_slang --no-synthesis-define --no-default-translate-off-format"
            f" {SOLUTION} --top {top}{overrides}",
            f"tee -q -o {CHECK_RTL} check",
            f"synth -top {top} -flatten",
            f"tee -q -o {LATCHES} select -count {LATCH_CELLS}",
            f"tee -q -o {LATCH_SOURCES} printattrs {LATCH_CELLS}",
            # sv-elab turns an incomplete always_comb into a loop, not a latch: only check sees it.
            f"tee -q -o {CHECK} check",
            # netlist_sim wraps the netlist into `top` with the parameters of the testbench.
            f"rename {top} {top}__netlist",
            f"write_verilog -noattr {NETLIST_GENERIC}",
            f"rename {top}__netlist {top}",
            f"dfflibmap -liberty {lib}",
            f"abc -liberty {lib}",
            f"hilomap -singleton -hicell {liberty.tie_high} -locell {liberty.tie_low}",
            "splitnets -ports",
            "opt_clean -purge",
            f"tee -q -o {STAT} stat -liberty {lib} -json",
            # -noff stops only at Yosys flops: the liberty flops are taken out of the selection.
            f"tee -q -o {LTP} ltp -noff * {flops} %d",
            f"write_verilog -noexpr -noattr {NETLIST}",
            "",
        ]
    )


def sta_script(top: str, clock: str | None, period_ns: float, liberty: Liberty = NANGATE45) -> str:
    """Constraints of the image, not of the solution (ADR-0007). Without a clock port a virtual
    clock times the paths from inputs to outputs."""
    lines = [f"read_liberty {liberty.path}", f"read_verilog {NETLIST}", f"link_design {top}"]
    if clock is None:
        lines += [f"create_clock -name clk -period {period_ns}", "set data_inputs [all_inputs]"]
    else:
        lines += [
            f"create_clock -name clk -period {period_ns} [get_ports {{{clock}}}]",
            f"set data_inputs [delete_from_list [all_inputs] [get_ports {{{clock}}}]]",
        ]
    lines += [
        "if {[llength $data_inputs]} {",
        "  set_input_delay 0 -clock clk $data_inputs",
        f"  set_driving_cell -lib_cell {liberty.driving_cell} $data_inputs",
        "}",
        "if {[llength [all_outputs]]} {",
        "  set_output_delay 0 -clock clk [all_outputs]",
        f"  set pin [get_lib_pins {liberty.library}/{liberty.load_pin}]",
        "  set_load [get_property $pin capacitance] [all_outputs]",
        "}",
        "report_checks -path_delay max -digits 3",
        f"set result [open {STA_RESULT} w]",
        'puts $result "{\\"wns_ns\\": [format %.6f [worst_slack -max]]}"',
        "close $result",
        "",
    ]
    return "\n".join(lines)


# --- tool output ---------------------------------------------------------------------------------

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_ERROR = re.compile(
    r"^(?:(?P<file>[^\s:]+):(?P<line>\d+)(?:\.(?P<col>\d+))?(?:-[\d.]+)?: )?ERROR: (?P<text>.+)$"
)
_FULL_LOG = "; see full log for details"  # the stage keeps no Yosys log: not for the console
_SOURCE = re.compile(rf"{re.escape(SOLUTION)}:(\d+)\.(\d+)")
# Warnings are demoted to messages (`-w`): "Suppressed Warning:" in the reports of `tee`.
_LOOP = re.compile(r"^(?:Suppressed )?Warning: found logic loop in module ")
_LOOP_WIRE = re.compile(r"^\s+wire \\(\S+)(?: \[\d+\])?(?: source: (.*))?$")
_DRIVERS = re.compile(
    r"^(?:Suppressed )?Warning: multiple conflicting drivers for [^.\s]+\.\\(\S+?)(?: \[\d+\])?:$"
)
_CHECK_END = re.compile(r"^Found and reported (\d+) problems?\.$", re.MULTILINE)
_COUNT = re.compile(r"^\s*(\d+) objects\.\s*$")
_LTP = re.compile(r"^Longest topological path in \S+ \(length=(\d+)\):$", re.MULTILINE)


class OutputError(ValueError):
    """A tool file that breaks its format: the stage reports OUTPUT_INVALID."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)


class _StatDesign(_Strict):
    num_cells: NonNegativeInt
    area: float = 0.0  # no cells, no "area" (S4)
    num_cells_by_type: dict[str, NonNegativeInt] = {}


class _Stat(_Strict):
    design: _StatDesign


class _StaResult(_Strict):
    wns_ns: float


def console_line(line: str) -> tuple[str | None, None]:
    return _ANSI.sub("", line).removesuffix(_FULL_LOG), None


def yosys_errors(output: str) -> list[Diagnostic]:
    """`ERROR:` lines of Yosys, with the place in the solution when there is one."""
    diagnostics = []
    for line in output.splitlines():
        found = _ERROR.match(_ANSI.sub("", line).strip())
        if found is None:
            continue
        text = found["text"].removesuffix(_FULL_LOG)
        located = found["file"] == SOLUTION
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="SYNTH_ERROR",
                message=text,
                file=SOLUTION if located else None,
                line=int(found["line"]) if located else None,
                col=int(found["col"]) if located and found["col"] else None,
            )
        )
    specific = [d for d in diagnostics if d.message != "Design elaboration failed"]
    return specific or diagnostics


def _file(run: ExecResult, name: str) -> str:
    if name not in run.files:
        raise OutputError(f"{name} is missing")
    try:
        return run.files[name].decode("utf-8")
    except UnicodeDecodeError as error:
        raise OutputError(f"{name}: {error}") from error


def latch_count(run: ExecResult) -> int:
    found = _COUNT.match(_file(run, LATCHES))
    if found is None:
        raise OutputError(f"{LATCHES}: no count")
    return int(found[1])


def latch_diagnostics(run: ExecResult, count: int) -> list[Diagnostic]:
    """One diagnostic per block that infers latches; the places are a hint, the count decides."""
    places: dict[tuple[int, int], None] = {}
    if LATCH_SOURCES in run.files:
        for found in _SOURCE.finditer(run.files[LATCH_SOURCES].decode("utf-8", "replace")):
            places.setdefault((int(found[1]), int(found[2])), None)
    message = (
        "латч: переменная этого блока сохраняет значение — always @* присваивает её не во всех"
        " ветвях"
    )
    if not places:
        return [Diagnostic(severity="error", code="LATCH", message=f"латчей в схеме: {count}")]
    return [
        Diagnostic(
            severity="error", code="LATCH", message=message, file=SOLUTION, line=line, col=col
        )
        for line, col in places
    ]


def check_diagnostics(text: str, *, loops: bool, drivers: bool) -> list[Diagnostic]:
    """Combinational loops and conflicting drivers from a `check` report; one diagnostic per
    signal."""
    if _CHECK_END.search(text) is None:
        raise OutputError("check: no summary line")
    found: dict[tuple[str, str], Diagnostic] = {}
    block: str | None = None
    for line in text.splitlines():
        if _LOOP.match(line):
            block = "loop"
            continue
        driven = _DRIVERS.match(line)
        if driven is not None:
            block = None
            name = driven[1]
            if not drivers:
                continue
            found.setdefault(
                ("drivers", name),
                Diagnostic(
                    severity="error",
                    code="MULTIPLE_DRIVERS",
                    message=f"у сигнала {name} несколько драйверов: синтез не может их объединить",
                ),
            )
            continue
        if not line.startswith((" ", "\t")):
            block = None
            continue
        wire = _LOOP_WIRE.match(line) if block == "loop" and loops else None
        if wire is not None:
            name, place = wire[1], _SOURCE.search(wire[2] or "")
            found.setdefault(
                ("loop", name),
                Diagnostic(
                    severity="error",
                    code="LOGIC_LOOP",
                    message=(
                        f"комбинационная петля через сигнал {name}: его значение зависит от него"
                        " самого — обычно always_comb присваивает его не во всех ветвях"
                    ),
                    file=SOLUTION if place else None,
                    line=int(place[1]) if place else None,
                    col=int(place[2]) if place else None,
                ),
            )
    return list(found.values())


def metrics(run: ExecResult, *, clocked: bool, period_ns: float, latches: int) -> SynthMetrics:
    try:
        stat = _Stat.model_validate_json(_file(run, STAT)).design
        sta = _StaResult.model_validate_json(_file(run, STA_RESULT))
    except ValidationError as error:
        raise OutputError(str(error)) from error
    depth = _LTP.search(_file(run, LTP))
    if depth is None:
        raise OutputError(f"{LTP}: no longest path")
    critical = 0.0 if sta.wns_ns >= NO_PATHS_SLACK else round(period_ns - sta.wns_ns, DELAY_DIGITS)
    if critical < 0:
        raise OutputError(f"{STA_RESULT}: slack {sta.wns_ns} over the period")
    cells = stat.num_cells_by_type
    return SynthMetrics(
        critical_path_ns=critical,
        fmax_mhz=round(1000 / critical, 2) if clocked and critical > 0 else None,
        area_um2=round(stat.area, AREA_DIGITS),
        cells=stat.num_cells,
        flops=sum(
            n for cell, n in cells.items() if any(fnmatchcase(cell, p) for p in NANGATE45.flops)
        ),
        latches=latches,
        logic_depth=int(depth[1]),
        liberty=NANGATE45.name,
        cells_by_type=dict(sorted(cells.items())),
    )


class SynthStage:
    stage_type: ClassVar[str] = "synth"
    config_model: ClassVar[type[BaseModel]] = SynthConfig
    metrics_schema: ClassVar[str | None] = "synth/v1"

    def plan(self, ctx: StageContext) -> StagePlan:
        assert isinstance(ctx.config, SynthConfig)
        top = ctx.problem.top
        params = synth_params(ctx.problem, ctx.config)
        clock = clock_port(ctx.problem)
        return StagePlan(
            commands=(
                # Errors only: -qq alone still prints the warnings of `check` in `synth`, one
                # block per looped bit, enough to hit the output limit.
                Command(("yosys", "-qq", "-w", ".*", "-s", YOSYS_SCRIPT)),
                Command(("sta", "-no_init", "-no_splash", "-exit", STA_SCRIPT)),
            ),
            timeout_s=ctx.limits.timeout_s,
            output_limit=ctx.limits.output_bytes,
            inputs={
                SOLUTION: canonical_solution(ctx),
                YOSYS_SCRIPT: yosys_script(top, params).encode(),
                STA_SCRIPT: sta_script(top, clock, ctx.config.clock_period_ns).encode(),
            },
            collect=(
                LATCHES,
                LATCH_SOURCES,
                CHECK_RTL,
                CHECK,
                STAT,
                LTP,
                STA_RESULT,
                NETLIST_GENERIC,
            ),
            collect_limit=FILE_LIMIT,
            line_filter=console_line,
            cache=True,
        )

    def interpret(self, ctx: StageContext, runs: Sequence[ExecResult]) -> StageOutcome:
        assert isinstance(ctx.config, SynthConfig)
        run = runs[-1]
        if run.timed_out:
            return StageOutcome(status="failed", failure_kind="limit", limit="time")
        if run.output_limited:
            return StageOutcome(status="failed", failure_kind="limit", limit="output")
        yosys = run.commands[0].exit_code
        if yosys == OOM_KILLED:
            return StageOutcome(status="failed", failure_kind="limit", limit="memory")
        if yosys != 0:
            errors = yosys_errors(run.output)
            if not errors:  # a crash, not a message about the code
                return StageOutcome(status="error", error_code="TOOL_FAILED")
            return _not_synthesizable("решение не синтезируется", errors)
        try:
            return self._synthesized(ctx.config, ctx.problem, run)
        except OutputError:
            return StageOutcome(status="error", error_code="OUTPUT_INVALID")

    def _synthesized(self, config: SynthConfig, problem: Problem, run: ExecResult) -> StageOutcome:
        latches = latch_count(run)
        found = latch_diagnostics(run, latches) if config.forbid_latches and latches else []
        for name, loops, drivers in (
            (CHECK_RTL, False, True),
            (CHECK, config.forbid_latches, False),
        ):
            if name in run.oversized:
                message = "Yosys check: слишком много замечаний"
                found.append(Diagnostic(severity="error", code="SYNTH_CHECK", message=message))
            else:
                found += check_diagnostics(_file(run, name), loops=loops, drivers=drivers)
        if found:
            codes = {d.code for d in found}
            caption = (
                "латчи в схеме"
                if codes == {"LATCH"}
                else "комбинационная петля"
                if codes == {"LOGIC_LOOP"}
                else "решение не синтезируется"
            )
            return _not_synthesizable(caption, found)
        sta = run.commands[1].exit_code if len(run.commands) > 1 else None
        if sta == OOM_KILLED:
            return StageOutcome(status="failed", failure_kind="limit", limit="memory")
        if sta != 0:
            return StageOutcome(status="error", error_code="TOOL_FAILED")
        if NETLIST_GENERIC in run.oversized:
            return StageOutcome(status="failed", failure_kind="limit", limit="output")
        if run.oversized - {LATCH_SOURCES}:  # the checks are above
            raise OutputError(f"oversized: {sorted(run.oversized)}")
        if NETLIST_GENERIC not in run.files:
            raise OutputError(f"{NETLIST_GENERIC} is missing")
        measured = metrics(
            run,
            clocked=clock_port(problem) is not None,
            period_ns=config.clock_period_ns,
            latches=latches,
        )
        return StageOutcome(
            status="passed",
            metrics=measured.model_dump(exclude_none=True),
            summary=StageSummary(caption=_caption(measured)),
            outputs={"netlist_generic": run.files[NETLIST_GENERIC]},
        )


def _caption(measured: SynthMetrics) -> str:
    delay, area = (
        f"{value:g}".replace(".", ",") for value in (measured.critical_path_ns, measured.area_um2)
    )
    return f"{delay} нс, {area} мкм², ячеек {measured.cells}"


def _not_synthesizable(caption: str, diagnostics: list[Diagnostic]) -> StageOutcome:
    return StageOutcome(
        status="failed",
        failure_kind="compile",
        summary=StageSummary(caption=caption, diagnostics=diagnostics[:MAX_DIAGNOSTICS]),
    )
