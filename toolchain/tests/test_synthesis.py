"""Synthesis in the image (ADR-0007): Yosys with sv-elab, OpenSTA, the Nangate45 liberty, the
`synth` stage on top of them (specs/07 §2.4) and the simulation of its netlist (§2.5)."""

import re
import shutil
import threading
import tomllib
from fnmatch import fnmatchcase
from pathlib import Path

import pytest

from judge.core.events import Event, LogEvent
from judge.core.executor import LocalDockerExecutor
from judge.core.leaderboard import leaderboard_metrics
from judge.core.limits import load_resource_classes, sandbox_limits, stage_limits
from judge.core.package import Problem, load_manifest
from judge.core.pipeline import CACHED_RUN_NOTE, Job, param_set_of, run_pipeline
from judge.core.registry import get_language
from judge.core.stage import FinishedStage, StageContext, StageResult
from judge.languages.systemverilog.stages.synth import (
    NANGATE45,
    NETLIST_GENERIC,
    SynthConfig,
    SynthStage,
)
from sandbox import IMAGE, RUNTIME, Sandbox, output

REPO = Path(__file__).parents[2]
CORPUS = sorted((REPO / "judge" / "tests" / "data" / "precheck" / "good").glob("*.sv"))
PACKAGE = REPO / "judge" / "tests" / "data" / "packages" / "counter"
RESOURCE_CLASSES = load_resource_classes(REPO / "config" / "resource-classes.yaml")
PDK = str(Path(NANGATE45.path).parent.as_posix())
READ_SLANG = "read_slang --no-synthesis-define --no-default-translate-off-format"

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
# Simulation does not tell these from a correct counter on the tests; synthesis does.
INCOMPLETE = HEADER + (
    "  logic [3:0] next;\n"
    "  always_comb begin\n"
    "    if (count == 4'd9) next = '0;\n"
    "    else if (count < 4'd9) next = count + 4'd1;\n"
    "  end\n"
    "  always_ff @(posedge clk)\n"
    "    if (rst) count <= '0;\n"
    "    else if (en) count <= next;\n"
    "endmodule\n"
)
UNSYNTHESIZABLE = {
    "loop": (INCOMPLETE, "LOGIC_LOOP", 3),
    "latch": (INCOMPLETE.replace("always_comb", "always @*"), "LATCH", 4),
    "drivers": (
        HEADER + "  always_ff @(posedge clk) if (rst) count <= '0;\n"
        "  always_ff @(posedge clk) if (en) count <= count + 4'd1;\nendmodule\n",
        "MULTIPLE_DRIVERS",
        None,
    ),
    "async-load": (
        HEADER + "  always_ff @(posedge clk or posedge rst or posedge en)\n"
        "    count <= rst ? '0 : count + 4'd1;\nendmodule\n",
        "SYNTH_ERROR",
        4,
    ),
}
# The references of the demo problems, synthesized in S4 (docs/spikes/s4.md), with the precision of
# the stage (ADR-0006: delay to 1 ps, area to 0.01 µm²; S4 reported 0.1 ps and 0.001 µm²):
# area µm², cells, flops, critical path ns, logic depth, fmax.
S4_METRICS = {
    "mux4": (41.76, 41, 0, 0.172, 3, None),
    "carry-adder": (47.35, 38, 0, 0.387, 9, None),
    "counter-mod-n": (34.58, 18, 4, 0.317, 3, 3154.57),
    "seq-detector": (31.92, 15, 5, 0.177, 2, 5649.72),
    "sync-fifo": (1194.87, 526, 145, 0.592, 7, 1689.19),
}


class Console:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []

    def emit(self, event: Event) -> None:
        if isinstance(event, LogEvent):
            self.lines.append((event.ch, event.text))


class MemoryCache:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def get(self, key: str) -> bytes | None:
        return self.files.get(key)

    def put(self, key: str, data: bytes) -> None:
        self.files[key] = data


def check(
    package: Path,
    solution: str | bytes,
    stages: tuple[str, ...] | None,
    cache: MemoryCache | None = None,
    problem: Problem | None = None,
) -> tuple[list[StageResult], Console]:
    problem = problem or load_manifest(package)
    code = solution.encode() if isinstance(solution, str) else solution
    job = Job(problem, package, "submit", seed=1, solution=code, stages=stages)
    sink = Console()
    with LocalDockerExecutor(
        IMAGE, sandbox_limits(problem, RESOURCE_CLASSES), runtime=RUNTIME
    ) as executor:
        results = run_pipeline(
            job,
            get_language("systemverilog"),
            executor,
            sink,
            RESOURCE_CLASSES,
            build_cache=cache or MemoryCache(),
        )
    assert results[0].status == "passed", results[0]
    return results, sink


def synthesize(
    package: Path, solution: str | bytes, cache: MemoryCache | None = None
) -> tuple[StageResult, Console]:
    results, sink = check(package, solution, ("precheck", "synth"), cache)
    return results[-1], sink


def reference(package: Path) -> bytes:
    manifest = load_manifest(package)
    assert manifest.reference is not None
    return (package / manifest.reference.solutions[0].file).read_bytes()


def yosys(sandbox: Sandbox, workdir: str, script: str) -> str:
    sandbox.write(f"{workdir}/script.ys", script)
    result = sandbox.exec(["yosys", "-q", "-s", "script.ys"], cwd=workdir, timeout=120)
    assert result.returncode == 0, output(result)
    return result.stdout.decode()


def test_slang_in_yosys_is_the_one_of_pyslang(sandbox: Sandbox, lock: dict[str, str]) -> None:
    """precheck (pyslang) and synth (sv-elab in Yosys) parse the code with one slang (ADR-0007)."""
    result = sandbox.exec(["yosys", "-Q", "-p", "slang_version"])
    assert result.returncode == 0, output(result)
    assert f"slang revision {lock['SLANG_COMMIT']}\n" in result.stdout.decode(), output(result)
    script = "import pyslang; print(pyslang.VersionInfo.getHash())"
    pyslang_hash = sandbox.exec(["python3", "-c", script]).stdout.decode().strip()
    assert len(pyslang_hash) >= 7
    assert lock["SLANG_COMMIT"].startswith(pyslang_hash)


@pytest.mark.parametrize("path", CORPUS, ids=[path.stem for path in CORPUS])
def test_corpus_solution_synthesizes_without_latches_and_loops(
    sandbox: Sandbox, workdir: str, path: Path
) -> None:
    """The legal constructs of precheck read in sv-elab and synthesize cleanly (S7)."""
    sandbox.write(f"{workdir}/solution.sv", path.read_text(encoding="utf-8"))
    yosys(
        sandbox,
        workdir,
        f"{READ_SLANG} solution.sv --top top\n"
        "synth -top top -flatten\n"
        "select -assert-none t:$_DLATCH* t:$_DLATCHSR* t:$_SR_* t:$dlatch* t:$sr\n"
        "check -assert\n",
    )


@pytest.mark.parametrize("problem", sorted(S4_METRICS))
def test_the_references_of_the_demo_problems_have_the_metrics_of_s4(problem: str) -> None:
    """The stage script gives what S4 measured: its extra checks do not change the design."""
    package = REPO / "problems" / problem
    synth, _ = synthesize(package, reference(package))
    assert synth.status == "passed", synth
    metrics = synth.metrics
    area, cells, flops, critical, depth, fmax = S4_METRICS[problem]
    assert (metrics["area_um2"], metrics["cells"], metrics["flops"]) == (area, cells, flops)
    assert (metrics["critical_path_ns"], metrics["logic_depth"]) == (critical, depth)
    assert metrics.get("fmax_mhz") == fmax
    assert (metrics["latches"], metrics["liberty"]) == (0, "nangate45")
    assert sum(metrics["cells_by_type"].values()) == cells


@pytest.mark.parametrize("case", sorted(UNSYNTHESIZABLE))
def test_unsynthesizable_solutions_fail_as_compile(case: str) -> None:
    solution, code, line = UNSYNTHESIZABLE[case]
    synth, sink = synthesize(PACKAGE, solution)
    assert (synth.status, synth.failure_kind) == ("failed", "compile"), synth
    assert [(d.code, d.line) for d in synth.summary.diagnostics] == [(code, line)]
    assert all("\x1b" not in text for _, text in sink.lines), "colors are removed"


def test_a_second_check_of_the_same_code_replays_the_stage_cache() -> None:
    cache = MemoryCache()
    first, _ = synthesize(PACKAGE, CORRECT, cache)
    second, sink = synthesize(PACKAGE, CORRECT, cache)
    assert (first.cached, second.cached) == (False, True)
    assert second.metrics == first.metrics
    assert ("sys", CACHED_RUN_NOTE) in sink.lines


def test_the_netlist_of_a_reference_passes_the_testbench_and_ranks_it() -> None:
    """netlist_sim (specs/07 §2.5) on a problem with parameters: the wrapper takes the testbench's
    `#(.WIDTH(WIDTH))` at every parameter set (ADR-0014), and the accepted Submit has the metrics
    of the formula, those of the primary set."""
    package = REPO / "problems" / "mux4"
    results, _ = check(package, reference(package), None)
    assert [(r.key, r.status) for r in results] == [
        ("precheck", "passed"),
        ("lint", "passed"),
        ("sim_full", "passed"),
        ("sim_full@narrow", "passed"),
        ("sim_full@wide", "passed"),
        ("synth", "passed"),
        ("synth@narrow", "passed"),
        ("synth@wide", "passed"),
        ("netlist_sim", "passed"),
        ("netlist_sim@narrow", "passed"),
        ("netlist_sim@wide", "passed"),
    ]
    for netlist_sim in results[-3:]:
        assert netlist_sim.metrics["tests_passed"] == netlist_sim.metrics["tests_total"] > 0
    assert leaderboard_metrics(load_manifest(package), results) == {
        "synth.critical_path_ns": S4_METRICS["mux4"][3],
        "synth.area_um2": S4_METRICS["mux4"][0],
    }


def test_a_testbench_with_other_parameters_than_synthesis_is_a_problem_error(
    tmp_path: Path,
) -> None:
    """The judge sets the testbench parameters to the values of the set (`-G`), so the netlist
    and the testbench disagree only when the testbench hard-codes a parameter of the design: a
    netlist synthesized for WIDTH=4 under `#(.WIDTH(8))`. `$fatal` of the wrapper stops the build
    under -Werror-USERFATAL (S4), not a wrong answer of the solution."""
    package = tmp_path / "mux4"
    shutil.copytree(REPO / "problems" / "mux4", package)
    tb_top = package / "tb" / "tb_top.sv"
    text = tb_top.read_text(encoding="utf-8")
    assert "mux4 #(.WIDTH(WIDTH)) dut" in text
    tb_top.write_text(text.replace("mux4 #(.WIDTH(WIDTH)) dut", "mux4 #(.WIDTH(8)) dut"), "utf-8")
    problem = load_manifest(package)
    parameters = [
        p.model_copy(update={"default": 4}) if p.name == "WIDTH" else p
        for p in problem.interface.parameters
    ]
    interface = problem.interface.model_copy(update={"parameters": parameters})
    narrow = problem.model_copy(update={"interface": interface})
    results, sink = check(
        package, reference(package), ("precheck", "synth", "netlist_sim"), problem=narrow
    )
    netlist_sim = results[-1]
    assert (netlist_sim.status, netlist_sim.error_code) == ("error", "NETLIST_PARAMS_MISMATCH")
    assert any("netlist synthesized for WIDTH=4" in text for _, text in sink.lines), sink.lines


def test_a_testbench_without_the_parameters_is_a_problem_error(tmp_path: Path) -> None:
    """The testbench top must declare a `parameter` for every parameter of the interface
    (specs/06 §3.1): Verilator does not build a `-G` it cannot apply."""
    package = tmp_path / "mux4"
    shutil.copytree(REPO / "problems" / "mux4", package)
    tb_top = package / "tb" / "tb_top.sv"
    text = tb_top.read_text(encoding="utf-8")
    header = "module tb_top #(\n  parameter int WIDTH = 8\n);\n"
    assert header in text
    localparam = "module tb_top;\n  localparam int WIDTH = 8;\n"
    tb_top.write_text(text.replace(header, localparam), "utf-8")
    results, _ = check(package, reference(package), ("precheck", "sim_full"))
    sim = results[-1]
    assert (sim.status, sim.error_code) == ("error", "TB_PARAMS_MISSING")
    assert sim.summary.caption == (
        "верхний модуль тестбенча не объявляет parameter для параметров задачи: WIDTH"
    )


def test_the_stage_run_is_byte_identical() -> None:
    """Metrics, reports and both netlists (S4: 300 runs on two machines)."""
    problem = load_manifest(PACKAGE)
    ctx = StageContext(
        key="synth",
        type="synth",
        ordinal=1,
        config=SynthConfig(),
        problem=problem,
        package_dir=PACKAGE,
        kind="submit",
        seed=1,
        solution=b"",
        limits=stage_limits(problem, "synth", "synth", RESOURCE_CLASSES),
        previous={
            "precheck": FinishedStage(
                StageResult(key="precheck", type="precheck", ordinal=0, status="passed"),
                {"solution.sv": CORRECT.encode()},
            )
        },
        param_set=param_set_of(problem, "default"),
    )
    plan = SynthStage().plan(ctx)
    files = []
    with LocalDockerExecutor(
        IMAGE, sandbox_limits(problem, RESOURCE_CLASSES), runtime=RUNTIME
    ) as executor:
        for _ in range(2):
            run = executor.run("synth", plan, lambda channel, text: None, threading.Event())
            assert run.ok, run.output
            files.append(dict(run.files))
    assert files[0] == files[1]
    assert NETLIST_GENERIC in files[0]


def test_the_flop_patterns_are_the_ff_cells_of_the_liberty(sandbox: Sandbox) -> None:
    """`flops` and the logic depth count liberty cells by name: exactly those with an `ff` group."""
    cells: dict[str, bool] = {}
    current = None
    for line in sandbox.read(NANGATE45.path).splitlines():
        found = re.match(r'\s*cell\s*\(\s*"?(\w+)"?\s*\)', line)
        if found:
            current = found[1]
            cells[current] = False
        elif current and re.match(r"\s*ff\s*\(", line):
            cells[current] = True
    assert any(cells.values())
    for cell, is_flop in cells.items():
        named = any(fnmatchcase(cell, pattern) for pattern in NANGATE45.flops)
        assert named == is_flop, cell


def test_the_liberty_of_the_stage_is_the_one_of_versions_lock(lock: dict[str, str]) -> None:
    """The profile names its liberty after the `<NAME>_LIB_SHA256` key (ToolchainProfile.liberty),
    the metrics after the stage: they must agree."""
    assert f"{NANGATE45.name.upper()}_LIB_SHA256" in lock
    assert Path(NANGATE45.path).name == "NangateOpenCellLibrary_typical.lib"


def test_nangate45_ships_with_license_and_source(sandbox: Sandbox, lock: dict[str, str]) -> None:
    """ADR-0007: LICENSE and README.md of OpenROAD-flow-scripts lie next to the unmodified liberty,
    and the license check has an explicit exception for it."""
    files = {
        "NangateOpenCellLibrary_typical.lib": lock["NANGATE45_LIB_SHA256"],
        "LICENSE": lock["NANGATE45_LICENSE_SHA256"],
        "README.md": lock["NANGATE45_README_SHA256"],
    }
    result = sandbox.exec(["sha256sum", *files], cwd=PDK)
    assert result.returncode == 0, output(result)
    sums = {}
    for line in result.stdout.decode().splitlines():
        digest, name = line.split()
        sums[name] = digest
    assert sums == files
    header = sandbox.exec(["head", "-c", "2048", NANGATE45.path]).stdout.decode()
    assert "Copyright (C) 2004-2011, Nangate Inc." in header
    assert "Version: PDKv1.3_v2010_12" in sandbox.read(f"{PDK}/README.md")

    policy = tomllib.loads((REPO / "scripts" / "license-policy.toml").read_text(encoding="utf-8"))
    exceptions = {(e["ecosystem"], e["name"]): e["adr"] for e in policy["exceptions"]}
    assert exceptions[("toolchain", "nangate45")] == "ADR-0007"


def test_licenses_of_the_synthesis_tools(sandbox: Sandbox) -> None:
    for path in (
        "/opt/licenses/yosys/COPYING",
        "/opt/licenses/yosys/libs/slang/LICENSE",
        "/opt/licenses/yosys/frontends/slang/lib/LICENSE",
        "/opt/licenses/yosys/abc/copyright.txt",
        "/opt/licenses/opensta/LICENSE",
        "/opt/licenses/cudd/LICENSE",
        "/opt/licenses/eigen/copyright",
    ):
        assert sandbox.exec(["test", "-s", path]).returncode == 0, path
