"""apx_tb_pkg in the image, end to end: the testbench writes the protocol, the judge parses it."""

import shlex
from dataclasses import dataclass

import pytest

from judge.languages.systemverilog import tbproto
from sandbox import APX_TB_PKG, SIM_FLAGS, Sandbox, output

# A counter; +bug makes it wrap after 9, the kind of error a test catches mid-run.
DUT = """\
module top (input logic clk, input logic rst, output logic [3:0] count, output logic [99:0] wide);
  bit bug = $test$plusargs("bug");
  always_ff @(posedge clk) count <= rst || (bug && count == 4'd9) ? 4'd0 : count + 4'd1;
  assign wide = {96'h0, count};
endmodule
"""

# Cycle k is the k-th rising edge at (10k - 5) ns; checks run on the falling edge at 10k ns.
TB = """\
module tb;
  import apx_tb_pkg::*;
  timeunit 1ns;
  timeprecision 1ps;

  logic clk = 0, rst = 1;
  logic [3:0] count, exp_count;
  logic [99:0] wide;
  top dut (.*);
  always #5 clk = ~clk;
  always @(posedge clk) apx_tick();

  task automatic count_to(int n);
    exp_count = 0;
    @(negedge clk) rst = 1;
    @(negedge clk) rst = 0;
    repeat (n) begin
      @(negedge clk);
      exp_count = exp_count + 1;
      `APX_CHECK(count, exp_count)
      `APX_CHECK_MSG(wide, {96'h0, exp_count}, "Счётчик \\"обнулился\\"\\t раньше")
    end
  endtask

  initial begin
    apx_suite_begin();
    $display("urandom=%0d", $urandom);
    if ($test$plusargs("misuse")) apx_test_end();
    if (apx_test_begin("t1", "короткий \\"счёт\\"", "public")) begin
      count_to(5);
      apx_test_end();
    end
    if (apx_test_begin("t2", "счёт через 9", "public")) begin
      if ($test$plusargs("hang")) repeat (1000) @(posedge clk);
      count_to(12);
      apx_test_end();
    end
    if (apx_test_begin("t3", "ещё раз", "public")) begin
      count_to(3);
      apx_test_end();
    end
    if (apx_test_begin("h1", "скрытый", "hidden")) begin
      count_to(3);
      apx_test_end();
    end
    apx_suite_end();
  end
endmodule
"""

NONCE = "5be1c0de"
LIMIT = 1 << 20


@dataclass(frozen=True)
class Run:
    exit_code: int
    stdout: str
    result: tbproto.TbResult


@pytest.fixture(scope="module")
def bench(sandbox: Sandbox) -> str:
    """The testbench built once, the way the sim stage builds it (specs/07 §2.3)."""
    workdir = sandbox.mkdtemp()
    sandbox.write(f"{workdir}/tb.sv", TB)
    sandbox.write(f"{workdir}/solution.sv", DUT)
    sources = [APX_TB_PKG, "tb.sv", "solution.sv"]
    result = sandbox.exec(["apx-verilate", *SIM_FLAGS, "--top-module", "tb", *sources], cwd=workdir)
    assert result.returncode == 0, output(result)
    assert "%Warning" not in output(result)
    return workdir


def run(sandbox: Sandbox, bench: str, *plusargs: str) -> Run:
    script = "rm -f out.jsonl; ./obj_dir/Vtb +apx_result=out.jsonl " + shlex.join(plusargs)
    simulated = sandbox.exec(["sh", "-c", script], cwd=bench)
    data = sandbox.exec(["cat", "out.jsonl"], cwd=bench).stdout
    result = tbproto.parse_result(data, max_bytes=LIMIT)
    return Run(simulated.returncode, simulated.stdout.decode(), result)


def statuses(result: tbproto.TbResult) -> list[tuple[str, str]]:
    return [(test.id, test.status) for test in result.tests]


def test_package_is_in_the_image(sandbox: Sandbox) -> None:
    assert "package apx_tb_pkg;" in sandbox.read(APX_TB_PKG)


def test_passing_run(sandbox: Sandbox, bench: str) -> None:
    passed = run(sandbox, bench, "+apx_seed=7")
    assert passed.exit_code == 0
    assert passed.result.start is not None
    assert passed.result.start.seed == 7
    assert passed.result.start.groups is None
    assert statuses(passed.result) == [
        ("t1", "passed"),
        ("t2", "passed"),
        ("t3", "passed"),
        ("h1", "passed"),
    ]
    assert passed.result.tests[0].name == 'короткий "счёт"'
    assert passed.result.end is not None
    assert passed.result.end.passed == 4
    assert "@@apx" not in passed.stdout  # no nonce, no progress lines


def test_failing_run(sandbox: Sandbox, bench: str) -> None:
    failed = run(sandbox, bench, "+bug", "+apx_groups=public")
    assert failed.exit_code == 0
    assert statuses(failed.result) == [("t1", "passed"), ("t2", "failed"), ("t3", "not_run")]
    assert failed.result.end is not None
    assert (failed.result.end.passed, failed.result.end.failed) == (1, 1)
    count, wide = failed.result.tests[1].mismatches  # both signals of the first failing cycle
    assert (count.signal, count.expected, count.actual) == ("count", "4'ha", "4'h0")
    assert count.hint is None
    assert wide.signal == "wide"
    assert wide.expected == "100'h" + "0" * 24 + "a"
    assert wide.hint == 'Счётчик "обнулился"\t раньше'  # JSON escaping of quotes and controls
    assert count.cycle == wide.cycle
    assert count.time_ps == count.cycle * 10_000  # picoseconds whatever the testbench timescale


def test_progress_lines(sandbox: Sandbox, bench: str) -> None:
    failed = run(sandbox, bench, "+bug", f"+apx_nonce={NONCE}")
    records, console = [], []
    for line in failed.stdout.splitlines():
        text, record = tbproto.split_progress(line, NONCE)
        console.append(text)
        if record is not None:
            records.append(record.event)
    assert records == [
        "suite_start",
        *["test_start", "test_end"] * 2,
        "test_skip",
        "test_skip",
        "suite_end",
    ]
    assert not any("mismatch" in text or NONCE in text for text in console)


def test_seed_drives_urandom(sandbox: Sandbox, bench: str) -> None:
    def urandom(seed: str) -> str:
        lines = run(sandbox, bench, seed).stdout.splitlines()
        return next(line for line in lines if line.startswith("urandom="))

    assert urandom("+apx_seed=1") == urandom("+apx_seed=1")
    assert urandom("+apx_seed=1") != urandom("+apx_seed=2")
    top = run(sandbox, bench, f"+apx_seed={2**64 - 1}").result.start
    assert top is not None
    assert top.seed == 2**64 - 1


def test_trace_window(sandbox: Sandbox, bench: str) -> None:
    first = run(sandbox, bench, "+bug", "+apx_seed=3").result.first_mismatch
    assert first is not None
    start, stop = max(0, first.cycle - 64), first.cycle + 1  # t2 is still running at stop
    traced = run(
        sandbox,
        bench,
        "+bug",
        "+apx_seed=3",
        f"+apx_trace_from={start}",
        f"+apx_trace_to={stop}",
        "+apx_trace_file=window.fst",
    )
    assert traced.result.first_mismatch == first
    assert traced.result.end is None
    assert statuses(traced.result)[-1] == ("t2", "running")  # stopped at the end of the window
    size = sandbox.exec(["stat", "-c", "%s", "window.fst"], cwd=bench).stdout.decode()
    assert int(size) > 0


def test_cycle_limit(sandbox: Sandbox, bench: str) -> None:
    hung = run(sandbox, bench, "+hang", "+apx_max_cycles=100")
    assert hung.result.abort is not None
    assert (hung.result.abort.reason, hung.result.abort.cycle) == ("max_cycles", 101)
    assert statuses(hung.result)[-1] == ("t2", "running")


def test_testbench_misuse_is_reported(sandbox: Sandbox, bench: str) -> None:
    broken = run(sandbox, bench, "+misuse")
    assert broken.exit_code != 0
    assert broken.result.abort is not None
    assert broken.result.abort.reason == "tb_error"
    assert broken.result.abort.message == "apx_test_end() outside a test"
