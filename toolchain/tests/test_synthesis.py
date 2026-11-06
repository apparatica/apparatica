"""Synthesis tools of the image (ADR-0007): Yosys with sv-elab, OpenSTA, the Nangate45 liberty.

The `synth` stage itself comes with T3.1b; these tests check that the tools run in the sandbox and
do what the stage script of specs/07 §2.4 relies on.
"""

import json
import re
import tomllib
from pathlib import Path

import pytest

from sandbox import Sandbox, output

REPO = Path(__file__).parents[2]
CORPUS = sorted((REPO / "judge" / "tests" / "data" / "precheck" / "good").glob("*.sv"))
NANGATE45 = "/opt/pdk/nangate45"
LIBERTY = f"{NANGATE45}/NangateOpenCellLibrary_typical.lib"
# The frontend of the synth stage: no implicit SYNTHESIS define, translate_off comments are plain
# comments, so the design is the same for synthesis and simulation (ADR-0007).
READ_SLANG = "read_slang --no-synthesis-define --no-default-translate-off-format"

COUNTER = """\
module top (input logic clk, input logic rst, output logic [3:0] count);
  always_ff @(posedge clk) count <= rst ? 4'd0 : count + 4'd1;
endmodule
"""

# The mapping part of the stage script (specs/07 §2.4).
MAP = f"""\
read_liberty -lib {LIBERTY}
{READ_SLANG} solution.sv --top top
synth -top top -flatten
dfflibmap -liberty {LIBERTY}
abc -liberty {LIBERTY}
hilomap -singleton -hicell LOGIC1_X1 Z -locell LOGIC0_X1 Z
splitnets -ports
opt_clean -purge
tee -q -o stat.json stat -liberty {LIBERTY} -json
write_verilog -noexpr -noattr netlist.v
"""

STA = f"""\
read_liberty {LIBERTY}
read_verilog netlist.v
link_design top
create_clock -name clk -period 2.0 [get_ports clk]
set_input_delay 0 -clock clk [delete_from_list [all_inputs] [get_ports clk]]
set_output_delay 0 -clock clk [all_outputs]
set_driving_cell -lib_cell BUF_X1 [delete_from_list [all_inputs] [get_ports clk]]
set_load 0.00114 [all_outputs]
puts "worst_slack [worst_slack -max]"
"""


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


def test_counter_maps_to_nangate45_and_is_timed(sandbox: Sandbox, workdir: str) -> None:
    sandbox.write(f"{workdir}/solution.sv", COUNTER)
    yosys(sandbox, workdir, MAP)
    stat = json.loads(sandbox.read(f"{workdir}/stat.json"))["design"]
    flops = {cell: n for cell, n in stat["num_cells_by_type"].items() if cell.startswith("DFF")}
    assert sum(flops.values()) == 4, stat
    assert stat["area"] > 0

    sandbox.write(f"{workdir}/sta.tcl", STA)
    sta = sandbox.exec(["sta", "-no_init", "-exit", "sta.tcl"], cwd=workdir, timeout=60)
    assert sta.returncode == 0, output(sta)
    match = re.search(r"^worst_slack (\S+)$", sta.stdout.decode(), re.MULTILINE)
    assert match, output(sta)
    critical_path_ns = 2.0 - float(match.group(1))
    assert 0 < critical_path_ns < 2.0


def test_synthesis_is_deterministic(sandbox: Sandbox) -> None:
    """Two runs give byte-identical metrics and netlist (S4: 300 runs on two machines)."""
    results = []
    for _ in range(2):
        workdir = sandbox.mkdtemp()
        sandbox.write(f"{workdir}/solution.sv", COUNTER)
        yosys(sandbox, workdir, MAP)
        results.append((sandbox.read(f"{workdir}/stat.json"), sandbox.read(f"{workdir}/netlist.v")))
    assert results[0] == results[1]


def test_nangate45_ships_with_license_and_source(sandbox: Sandbox, lock: dict[str, str]) -> None:
    """ADR-0007: LICENSE and README.md of OpenROAD-flow-scripts lie next to the unmodified liberty,
    and the license check has an explicit exception for it."""
    files = {
        "NangateOpenCellLibrary_typical.lib": lock["NANGATE45_LIB_SHA256"],
        "LICENSE": lock["NANGATE45_LICENSE_SHA256"],
        "README.md": lock["NANGATE45_README_SHA256"],
    }
    result = sandbox.exec(["sha256sum", *files], cwd=NANGATE45)
    assert result.returncode == 0, output(result)
    sums = {}
    for line in result.stdout.decode().splitlines():
        digest, name = line.split()
        sums[name] = digest
    assert sums == files
    header = sandbox.exec(["head", "-c", "2048", LIBERTY]).stdout.decode()
    assert "Copyright (C) 2004-2011, Nangate Inc." in header
    assert "Version: PDKv1.3_v2010_12" in sandbox.read(f"{NANGATE45}/README.md")

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
