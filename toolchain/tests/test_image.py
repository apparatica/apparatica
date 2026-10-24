"""Smoke tests of the toolchain image: `just toolchain-build && just toolchain-test`."""

import json
import re
import time

import pytest

from sandbox import SANDBOX_UID, Sandbox, output

ERR_MARK = b"\x1e"
# The `sim` stage flags that apx-verilate does not add (specs/07 §2.3).
SIM_FLAGS = ["--x-assign", "unique", "--x-initial", "unique", "-Wno-fatal", "-Wno-lint", "-j", "2"]

COUNTER = """\
module top (input logic clk, input logic rst, output logic [3:0] count);
  always_ff @(posedge clk) count <= rst ? 4'd0 : count + 4'd1;
endmodule
"""

COUNTER_TB = """\
module tb;
  logic clk = 0, rst = 1;
  logic [3:0] count;
  top dut (.*);
  always #5 clk = ~clk;
  initial begin
    $dumpfile("trace.fst");
    $dumpvars(0, tb);
    repeat (2) @(posedge clk);
    @(negedge clk) rst = 0;  // away from the active edge: no race with always_ff
    repeat (10) @(posedge clk);
    #1 $display("count=%0d", count);
    $finish;
  end
endmodule
"""

RANDOMIZE_TB = """\
class Pair;
  rand bit [7:0] a, b;
  constraint sum_c { a + b == 8'd100; a > 8'd10; }
endclass

module tb;
  initial begin
    static Pair p = new;
    for (int i = 0; i < 5; i++) begin
      if (!p.randomize()) $fatal(1, "randomize failed");
      if (8'(p.a + p.b) != 8'd100 || p.a <= 8'd10) $fatal(1, "constraint violated");
    end
    $display("randomize ok");
    $finish;
  end
endmodule
"""


def build(sandbox: Sandbox, workdir: str, tb: str, solution: str | None = None) -> str:
    sandbox.write(f"{workdir}/tb.sv", tb)
    sources = ["tb.sv"]
    if solution is not None:
        sandbox.write(f"{workdir}/solution.sv", solution)
        sources.append("solution.sv")
    result = sandbox.exec(["apx-verilate", *SIM_FLAGS, "--top-module", "tb", *sources], cwd=workdir)
    assert result.returncode == 0, output(result)
    return result.stdout.decode()


class TestVersions:
    def test_lock_has_no_empty_values(self, lock: dict[str, str]) -> None:
        assert [key for key, value in lock.items() if not value] == []

    @pytest.mark.parametrize(
        ("argv", "pattern"),
        [
            (["verilator", "--version"], r"^Verilator {VERILATOR_VERSION}\b"),
            (["verible-verilog-syntax", "--version"], r"\b{VERIBLE_VERSION}\b"),
            (["z3", "--version"], r"^Z3 version {Z3_VERSION}\b"),
            (["g++", "-dumpfullversion"], r"^{GCC_VERSION}$"),
            (["python3", "--version"], r"^Python {PYTHON_VERSION}$"),
            (
                ["python3", "-c", "import importlib.metadata as m; print(m.version('pyslang'))"],
                r"^{PYSLANG_VERSION}$",
            ),
        ],
        ids=["verilator", "verible", "z3", "gcc", "python", "pyslang"],
    )
    def test_tool_matches_lock(
        self, sandbox: Sandbox, lock: dict[str, str], argv: list[str], pattern: str
    ) -> None:
        result = sandbox.exec(argv)
        expected = pattern.format(**{key: re.escape(value) for key, value in lock.items()})
        assert re.search(expected, result.stdout.decode(), re.MULTILINE), output(result)


class TestSandbox:
    def test_runs_as_unprivileged_user(self, sandbox: Sandbox) -> None:
        assert sandbox.exec(["id", "-u"]).stdout.decode().strip() == str(SANDBOX_UID)
        assert sandbox.exec(["sh", "-c", "echo $HOME"]).stdout.decode().strip() == "/work"

    def test_root_filesystem_is_read_only(self, sandbox: Sandbox) -> None:
        assert sandbox.exec(["touch", "/opt/apx/probe"]).returncode != 0

    def test_work_is_writable(self, sandbox: Sandbox, workdir: str) -> None:
        assert sandbox.exec(["touch", f"{workdir}/probe"]).returncode == 0

    def test_no_network(self, sandbox: Sandbox) -> None:
        result = sandbox.exec(["cat", "/sys/class/net/eth0/address"])
        assert result.returncode != 0


class TestVerilator:
    def test_simulation_with_fst_trace(self, sandbox: Sandbox, workdir: str) -> None:
        build(sandbox, workdir, COUNTER_TB, COUNTER)
        sim = sandbox.exec(
            ["obj_dir/Vtb", "+verilator+seed+7", "+verilator+rand+reset+2"], cwd=workdir
        )
        assert sim.returncode == 0, output(sim)
        assert "count=10" in sim.stdout.decode()
        size = sandbox.exec(["stat", "-c", "%s", f"{workdir}/trace.fst"]).stdout.decode()
        assert int(size) > 0

    def test_prebuilt_runtime_is_not_recompiled(self, sandbox: Sandbox, workdir: str) -> None:
        log = build(sandbox, workdir, COUNTER_TB, COUNTER)
        assert re.findall(r"\b(verilated\w*)\.cpp\b", log) == []
        assert "libverilated_apx.a" in log

    def test_constrained_randomization_uses_z3(self, sandbox: Sandbox, workdir: str) -> None:
        build(sandbox, workdir, RANDOMIZE_TB)
        sim = sandbox.exec(["obj_dir/Vtb", "+verilator+seed+1"], cwd=workdir)
        assert sim.returncode == 0, output(sim)
        assert "randomize ok" in sim.stdout.decode()
        # Without the solver on PATH randomization fails, so the run above did use Z3.
        no_z3 = sandbox.exec(
            ["obj_dir/Vtb", "+verilator+seed+1"], cwd=workdir, env={"PATH": "/nonexistent"}
        )
        assert "randomize ok" not in no_z3.stdout.decode()


def test_pyslang_parses_module(sandbox: Sandbox) -> None:
    script = (
        "import json, sys\n"
        "from pyslang import syntax\n"
        "tree = syntax.SyntaxTree.fromText(sys.stdin.read())\n"
        "print(json.dumps({'diagnostics': len(tree.diagnostics), 'kind': tree.root.kind.name,"
        " 'name': tree.root.header.name.valueText}))\n"
    )
    result = sandbox.exec(["python3", "-c", script], stdin=COUNTER.encode())
    assert result.returncode == 0, output(result)
    # A single top-level declaration is the root itself.
    assert json.loads(result.stdout) == {
        "diagnostics": 0,
        "kind": "ModuleDeclaration",
        "name": "top",
    }


def test_verible_syntax_and_lint(sandbox: Sandbox, workdir: str) -> None:
    sandbox.write(f"{workdir}/top.sv", COUNTER)
    syntax = sandbox.exec(["verible-verilog-syntax", f"{workdir}/top.sv"])
    assert syntax.returncode == 0, output(syntax)
    lint = sandbox.exec(["verible-verilog-lint", f"{workdir}/top.sv"])
    assert lint.returncode in (0, 1), output(lint)  # 1 = style findings


class TestApxRun:
    STREAMS = "echo out1; echo err1 >&2; sleep 0.2; echo out2; printf 'e2\\n\\ne3\\n' >&2"

    def test_marks_stderr_lines(self, sandbox: Sandbox) -> None:
        result = sandbox.exec(["apx-run", "sh", "-c", self.STREAMS])
        lines = result.stdout.split(b"\n")
        for line in (b"out1", b"out2", b"err1", b"e2", b"", b"e3"):
            expected = line if line.startswith(b"out") else ERR_MARK + line
            assert expected in lines, result.stdout
        assert b"\r" not in result.stdout
        assert result.stderr == b""

    def test_marks_stderr_lines_under_docker_tty(self, sandbox: Sandbox) -> None:
        # How the orchestrator runs stages: `docker exec -t` merges stderr into stdout.
        result = sandbox.exec(["apx-run", "sh", "-c", self.STREAMS], tty=True)
        lines = result.stdout.replace(b"\r\n", b"\n").split(b"\n")
        assert b"out1" in lines
        assert ERR_MARK + b"err1" in lines

    def test_command_sees_terminals(self, sandbox: Sandbox) -> None:
        result = sandbox.exec(["apx-run", "sh", "-c", "test -t 1 && test -t 2 && echo tty"])
        assert result.stdout == b"tty\n"

    @pytest.mark.parametrize(
        ("argv", "status"),
        [
            (["sh", "-c", "exit 3"], 3),
            (["sh", "-c", "kill -KILL $$"], 128 + 9),
            (["/nonexistent"], 127),
        ],
        ids=["exit-code", "signal", "not-found"],
    )
    def test_exit_status(self, sandbox: Sandbox, argv: list[str], status: int) -> None:
        assert sandbox.exec(["apx-run", *argv]).returncode == status

    def test_does_not_wait_for_leftover_processes(self, sandbox: Sandbox) -> None:
        # The leftover sleep keeps both terminals open; in a stage the orchestrator kills it.
        started = time.monotonic()
        result = sandbox.exec(["apx-run", "sh", "-c", "sleep 15 & echo done"], timeout=30)
        assert result.returncode == 0
        assert b"done" in result.stdout
        assert time.monotonic() - started < 10
