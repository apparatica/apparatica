"""The precheck runner in-process (pyslang is a dev dependency of the judge)."""

import json
from pathlib import Path
from typing import Any

import pytest
from pyslang import ast, syntax

from judge.languages.systemverilog.sandbox import precheck_runner as runner

DATA = Path(__file__).parent / "data" / "precheck"
LIMITS = runner.Limits(
    max_bytes=64 * 1024,
    max_lines=2000,
    max_state_bits=1 << 20,
    max_generate_steps=10_000,
    max_constexpr_steps=100_000,
)
PORTS = [
    {"name": "clk", "dir": "input", "width": "1", "signed": False},
    {"name": "a", "dir": "input", "width": "8", "signed": False},
    {"name": "y", "dir": "output", "width": "8", "signed": False},
]
JOB = runner.Job("top", [], PORTS, LIMITS)
HEADER = "module top (input logic clk, input logic [7:0] a, output logic [7:0] y);\n"


def body(text: str) -> str:
    return HEADER + text + "\nendmodule\n"


def check(code: str, job: runner.Job = JOB) -> runner.Result:
    return runner.precheck(code, job)


def categories(result: runner.Result) -> set[str]:
    return {f.category for f in result.findings}


def job_from(code: str) -> runner.Job:
    """The interface of a legal solution as problem.yaml would declare it."""
    compilation = ast.Compilation()
    compilation.addSyntaxTree(syntax.SyntaxTree.fromText(code))
    top = compilation.getRoot().topInstances[0]
    directions = {"In": "input", "Out": "output", "InOut": "inout"}
    ports = [
        {
            "name": p.name,
            "dir": directions[p.direction.name],
            "width": str(p.type.bitWidth),
            "signed": p.type.isSigned,
        }
        for p in top.body.portList
    ]
    parameters = [
        {"name": p.name, "type": "int", "default": int(p.value.value)}
        for p in top.body.parameters
        if not p.isLocalParam
    ]
    return runner.Job(top.name, parameters, ports, LIMITS)


@pytest.mark.parametrize("path", sorted(DATA.glob("good/*.sv")), ids=lambda p: p.stem)
def test_legal_solutions_pass(path: Path) -> None:
    code = path.read_text(encoding="utf-8")
    result = check(code, job_from(code))
    assert result.findings == []
    assert result.ports_ok is True
    assert result.module == "top"
    assert result.canonical is not None
    assert result.state_bits is not None


# (name, code, expected category) — specs/09 §4.2 precheck cases and specs/07 §2.1, from S7.
BAD: list[tuple[str, str, str]] = [
    ("$c", body('assign y = a;\ninitial $c("system(\\"id\\")");'), "forbidden"),
    ("$system", body('always_comb begin y = a; $system("id"); end'), "forbidden"),
    ("dpi_import", body('import "DPI-C" function int f();\nassign y = a;'), "forbidden"),
    ("systemc_header", "`systemc_header\n#include <cstdlib>\n`systemc_header_end\n" + body("assign y = a;"), "forbidden"),
    ("$fopen", body('integer fd;\nalways_comb begin fd = $fopen("/tmp/x", "w"); y = a; end'), "forbidden"),
    ("$readmemh", body('logic [7:0] m [4];\nalways_comb $readmemh("/etc/passwd", m);\nassign y = m[0];'), "forbidden"),
    ("include", '`include "/etc/passwd"\n' + body("assign y = a;"), "forbidden"),
    ("$value$plusargs", body('int s;\nalways_comb begin void\'($value$plusargs("apx_nonce=%d", s)); y = a; end'), "forbidden"),
    ("$root", body("assign y = $root.tb.secret;"), "forbidden"),
    ("import_pkg", body("import apx_tb_pkg::*;\nassign y = a;"), "forbidden"),
    ("scope_pkg", body("assign y = apx_tb_pkg::nonce[7:0];"), "forbidden"),
    ("ifdef_synthesis", body("`ifdef SYNTHESIS\nassign y = a;\n`else\nassign y = ~a;\n`endif"), "forbidden"),
    ("ifdef_verilator", body("`ifdef VERILATOR\nassign y = 8'h0;\n`endif"), "forbidden"),
    ("define", "`define A 8'h1\n" + body("assign y = `A;"), "forbidden"),
    ("macro_paste", body("assign y = a``b;"), "forbidden"),
    ("$fdisplay", body('always_comb begin y = a; $fdisplay(32\'h8000_0002, "x"); end'), "forbidden"),
    ("initial", body("initial y = 8'h1;"), "forbidden"),
    ("delay", body("assign #5 y = a;"), "forbidden"),
    ("delay_stmt", body("always_ff @(posedge clk) #1 y <= a;"), "forbidden"),
    ("fork", body("always_comb begin fork y = a; join end"), "forbidden"),
    ("upward_ref", body("assign y = tb.secret;"), "compile"),
    ("two_modules", body("assign y = a;") + "module helper; endmodule\n", "compile"),
    ("wrong_name", "module solution (input logic clk, input logic [7:0] a, output logic [7:0] y);\nassign y = a;\nendmodule\n", "compile"),
    ("nested_module", body("module inner; endmodule\nassign y = a;"), "forbidden"),
    ("unit_scope_decl", "localparam int K = 1;\n" + body("assign y = a;"), "forbidden"),
    ("interface", "interface bus; endinterface\n" + body("assign y = a;"), "forbidden"),
    ("class", body("class C; endclass\nassign y = a;"), "forbidden"),
    ("package", "package p; endpackage\n" + body("assign y = a;"), "forbidden"),
    ("bind", body("bind top helper h();\nassign y = a;"), "forbidden"),
    ("instantiation", body("top u (.clk(clk), .a(a), .y());\nassign y = a;"), "forbidden"),
    ("attribute", body("(* keep *) logic t;\nassign y = a;"), "forbidden"),
    ("task", body("task automatic t(); endtask\nassign y = a;"), "forbidden"),
    ("static_function", body("function int f(); return 1; endfunction\nassign y = a;"), "forbidden"),
    ("real", body("real r;\nassign y = a;"), "forbidden"),
    ("string", body("string s;\nassign y = a;"), "forbidden"),
    ("event", body("event e;\nassign y = a;"), "forbidden"),
    ("always_latch", body("always_latch if (clk) y = a;"), "forbidden"),
    ("always_no_event", body("always y = a;"), "forbidden"),
    ("event_in_body", body("always_comb begin @(posedge clk); y = a; end"), "forbidden"),
    ("wait", body("always_ff @(posedge clk) begin wait (a[0]); y <= a; end"), "forbidden"),
    ("force", body("always_comb begin force y = a; end"), "forbidden"),
    ("procedural_assign", body("always_comb begin assign y = a; end"), "forbidden"),
    ("final", body('final $display("bye");\nassign y = a;'), "forbidden"),
    ("$urandom", body("always_ff @(posedge clk) y <= 8'($urandom);"), "forbidden"),
    ("$time", body("always_ff @(posedge clk) y <= 8'($time);"), "forbidden"),
    ("$finish", body("always_ff @(posedge clk) begin y <= a; $finish; end"), "forbidden"),
    ("$error", body('always_comb begin y = a; if (a == 0) $error("zero"); end'), "forbidden"),
    ("while", body("always_comb begin int i = 0; while (i < 4) i++; y = a; end"), "forbidden"),
    ("forever", body("always_comb forever y = a;"), "forbidden"),
    ("repeat", body("always_comb repeat (2) y = a;"), "forbidden"),
    ("let", body("let f(x) = x;\nassign y = a;"), "forbidden"),
    ("checker", "checker c; endchecker\n" + body("assign y = a;"), "forbidden"),
    ("assert_property", body("assert property (@(posedge clk) a == a);\nassign y = a;"), "forbidden"),
    ("immediate_assert", body("always_comb begin y = a; assert (a == a); end"), "forbidden"),
    ("specify", body("specify endspecify\nassign y = a;"), "forbidden"),
    ("primitive", "primitive p(o, i); output o; input i; table 0:0; 1:1; endtable endprimitive\n" + body("assign y = a;"), "forbidden"),
    ("config", body("assign y = a;") + "config cfg; design top; endconfig\n", "forbidden"),
    ("event_trigger", body("always_comb begin ->e; y = a; end"), "forbidden"),
    ("deassign", body("always_comb begin deassign y; y = a; end"), "forbidden"),
    ("time_literal", body("localparam int T = 1ns;\nassign y = a;"), "forbidden"),
    ("void_cast", body("function automatic int f(); return 1; endfunction\nalways_comb begin void'(f()); y = a; end"), "forbidden"),
    ("huge_vector", body("logic [2**30-1:0] m;\nassign y = m[7:0];"), "compile"),
    ("huge_array", body("logic [7:0] m [2**24];\nassign y = m[0];"), "limit"),
    ("generate_bomb", body("for (genvar i = 0; i < 100000000; i++) begin : g\n  logic t;\nend\nassign y = a;"), "compile"),
    ("syntax_error", body("assign y = a +;"), "compile"),
]  # fmt: skip


@pytest.mark.parametrize(("code", "category"), [c[1:] for c in BAD], ids=[c[0] for c in BAD])
def test_rejected_solutions(code: str, category: str) -> None:
    result = check(code)
    assert result.findings, "expected a finding"
    assert result.findings[0].category == category, result.findings


def test_preprocessor_is_rejected_before_parsing() -> None:
    result = check(body("`ifdef SYNTHESIS\nassign y = a;\n`endif"))
    assert result.canonical is None  # nothing was parsed
    first = result.findings[0]
    assert (first.code, first.line, first.col) == ("PREPROCESSOR", 2, 1)
    assert "используйте localparam" in first.message


def test_forbidden_system_task_location() -> None:
    lines = ["assign y = a;"] + [""] * 9 + ['always_comb $system("ls");']
    finding = check(body("\n".join(lines))).findings[0]
    assert (finding.code, finding.line) == ("SYSTEM_TASK", 12)
    assert "$system" in finding.message


@pytest.mark.parametrize(
    ("code", "fragment"),
    [
        (body("initial y = 8'h1;"), "не синтезируется"),
        (body("assign #5 y = a;"), "задержки # не синтезируются"),
        (body("bind top helper h();"), "один модуль"),
    ],
)
def test_explanations(code: str, fragment: str) -> None:
    assert fragment in check(code).findings[0].message


def test_unlisted_kind_gets_the_generic_explanation() -> None:
    # A construct with no explanation of its own: forbidden by default, like any new slang kind.
    code = body("always_comb begin randcase 1: y = a; endcase end")
    finding = check(code).findings[0]
    assert finding.category == "forbidden"
    assert "не входит в синтезируемое подмножество" in finding.message


def test_kind_names_exist() -> None:
    # Loading the module resolves every kind name; this pins that the tables are not empty.
    assert len(runner.ALLOWED_NODES) > 100
    assert len(runner.FORBIDDEN_EXPLANATIONS) > 30


def test_comment_directives_disappear_and_positions_stay() -> None:
    code = (
        body(
            "// synthesis translate_off\n"
            "assign y = ~a; // verilator lint_off WIDTH\n"
            "// synthesis translate_on\n"
            "/* verilator public */ logic t;\n"
            "/* многострочный\n   комментарий */"
        )
        + "// after endmodule\n"
    )
    result = check(code)
    assert result.findings == []
    assert result.canonical is not None
    for word in ("translate", "verilator", "многострочный", "after"):
        assert word not in result.canonical
    original, canonical = code.splitlines(), result.canonical.splitlines()
    assert len(canonical) == len(original)
    assert canonical[2] == "assign y = ~a;" + " " * len(" // verilator lint_off WIDTH")
    assert canonical[4].index("logic") == original[4].index("logic")


def test_error_line_after_multiline_comment() -> None:
    code = body("/*\n\n\n*/\nassign y = a +;")
    assert (check(code).findings[0].line, check(code).findings[0].col) == (6, 15)


def interface_job(ports: list[dict[str, Any]], parameters: list[dict[str, Any]]) -> runner.Job:
    return runner.Job("sync_fifo", parameters, ports, LIMITS)


FIFO_PORTS = [
    {"name": "clk", "dir": "input", "width": "1", "signed": False},
    {"name": "rdata", "dir": "output", "width": "WIDTH", "signed": False},
    {"name": "count", "dir": "output", "width": "$clog2(DEPTH)+1", "signed": False},
]
FIFO_PARAMS = [
    {"name": "WIDTH", "type": "int", "default": 8},
    {"name": "DEPTH", "type": "int", "default": 16},
]


def fifo(header: str, extra: str = "") -> str:
    return f"module sync_fifo {header};\n{extra}endmodule\n"


GOOD_HEADER = (
    "#(parameter int WIDTH = 8, parameter int DEPTH = 16) "
    "(input logic clk, output logic [WIDTH-1:0] rdata, output logic [$clog2(DEPTH):0] count)"
)


def test_interface_matches() -> None:
    result = check(fifo(GOOD_HEADER), interface_job(FIFO_PORTS, FIFO_PARAMS))
    assert result.findings == []
    assert result.ports_ok is True


def test_interface_uses_problem_defaults_not_the_solution_ones() -> None:
    header = GOOD_HEADER.replace("WIDTH = 8", "WIDTH = 4")
    assert check(fifo(header), interface_job(FIFO_PORTS, FIFO_PARAMS)).findings == []


@pytest.mark.parametrize(
    ("header", "code", "message"),
    [
        (GOOD_HEADER.replace("[WIDTH-1:0] rdata", "[3:0] rdata"), "PORT_WIDTH",
         "порт rdata: ожидается ширина WIDTH (8), объявлено 4"),
        (GOOD_HEADER.replace("input logic clk, ", ""), "PORT_MISSING", "нет порта clk"),
        (GOOD_HEADER.replace("input logic clk", "input logic clk, input logic en"), "PORT_EXTRA",
         "лишний порт en"),
        (GOOD_HEADER.replace("input logic clk", "output logic clk"), "PORT_DIRECTION",
         "порт clk: ожидается input, объявлен output"),
        (GOOD_HEADER.replace("output logic [WIDTH", "output logic signed [WIDTH"), "PORT_SIGNED",
         "порт rdata: ожидается беззнаковый"),
        (GOOD_HEADER.replace(", parameter int DEPTH = 16", "").replace("$clog2(DEPTH)", "4"),
         "PARAM_MISSING", "нет параметра DEPTH"),
        (GOOD_HEADER.replace("DEPTH = 16", "DEPTH = 16, parameter int X = 1"), "PARAM_EXTRA",
         "лишний параметр X: используйте localparam"),
    ],
)  # fmt: skip
def test_interface_mismatch(header: str, code: str, message: str) -> None:
    result = check(fifo(header), interface_job(FIFO_PORTS, FIFO_PARAMS))
    assert [(f.category, f.code, f.message) for f in result.findings] == [
        ("compile", code, message)
    ]
    assert result.ports_ok is False


def test_module_count_message_names_the_top() -> None:
    code = fifo(GOOD_HEADER) + "module helper; endmodule\n"
    finding = check(code, interface_job(FIFO_PORTS, FIFO_PARAMS)).findings[0]
    assert (finding.category, finding.message) == (
        "compile",
        "в решении должен быть ровно один модуль sync_fifo",
    )


def test_size_limits() -> None:
    small = runner.Limits(100, 3, 1 << 20, 10_000, 100_000)
    job = runner.Job("top", [], PORTS, small)
    too_big = check(body("assign y = a;" + " " * 200), job).findings[0]
    assert (too_big.category, too_big.code, too_big.limit) == ("limit", "CODE_SIZE", "size")
    too_long = check("\n" * 5 + "module top; endmodule\n", job).findings[0]
    assert "строк" in too_long.message


def test_state_limit() -> None:
    finding = check(body("logic [7:0] m [2**24];\nassign y = m[0];")).findings[0]
    assert (finding.code, finding.limit) == ("STATE_SIZE", "memory")


def test_main_writes_result_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    job = {"top": "top", "parameters": [], "ports": PORTS, "limits": vars(LIMITS)}
    (tmp_path / "job.json").write_text(json.dumps(job), encoding="utf-8")
    (tmp_path / "solution.sv").write_text(body("assign y = a; // ok"), encoding="utf-8")
    assert runner.main(["runner", "job.json", "solution.sv"]) == 0
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result.pop("ast_hash").startswith("n1:")
    assert result == {"v": 1, "findings": [], "module": "top", "ports_ok": True, "state_bits": 17}
    assert "// ok" not in (tmp_path / "canonical.sv").read_text(encoding="utf-8")


def test_main_rejects_invalid_utf8(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    job = {"top": "top", "parameters": [], "ports": PORTS, "limits": vars(LIMITS)}
    (tmp_path / "job.json").write_text(json.dumps(job), encoding="utf-8")
    (tmp_path / "solution.sv").write_bytes(b"module top; \xff endmodule\n")
    runner.main(["runner", "job.json", "solution.sv"])
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result["findings"][0]["code"] == "ENCODING"
    assert not (tmp_path / "canonical.sv").exists()
