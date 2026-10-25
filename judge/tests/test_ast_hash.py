"""Normalized AST hash (specs/07 §6, T0.7b): what it ignores and what it tells apart."""

import re

import pytest
from pyslang import syntax

from judge.languages.systemverilog.sandbox import precheck_runner as runner

LIMITS = runner.Limits(
    max_bytes=64 * 1024,
    max_lines=2000,
    max_state_bits=1 << 20,
    max_generate_steps=10_000,
    max_constexpr_steps=100_000,
)
PORTS = [
    {"name": "clk", "dir": "input", "width": "1", "signed": False},
    {"name": "a", "dir": "input", "width": "WIDTH", "signed": False},
    {"name": "y", "dir": "output", "width": "WIDTH", "signed": False},
]
JOB = runner.Job("top", [{"name": "WIDTH", "type": "int", "default": 8}], PORTS, LIMITS)

TEMPLATE = """\
module top #(parameter int WIDTH = 8) (
  input logic clk, input logic [WIDTH-1:0] a, output logic [WIDTH-1:0] y
);
  typedef logic [WIDTH-1:0] {word}_t;
  localparam {word}_t {mask} = {literal};
  {word}_t {acc};
  function automatic {word}_t {inv}(input {word}_t v);
    return ~v;
  endfunction
  for (genvar {i} = 0; {i} < 2; {i}++) begin : {block}
    logic {tap};
    assign {tap} = {acc}[{i}];
  end
  always_ff @(posedge clk) {acc} <= {acc} + (a & {mask});
  assign y = {inv}({acc});
endmodule
"""
NAMES = {
    "word": "word",
    "mask": "MASK",
    "acc": "acc",
    "inv": "inv",
    "i": "i",
    "block": "g_tap",
    "tap": "tap",
    "literal": "8'hFF",
}


def solution(**changes: str) -> str:
    return TEMPLATE.format(**(NAMES | changes))


def ast_hash(code: str) -> str:
    result = runner.precheck(code, JOB)
    assert result.findings == [], result.findings
    assert result.ast_hash is not None
    return result.ast_hash


BASE = ast_hash(solution())


def test_format() -> None:
    assert re.fullmatch(rf"n{runner.NORMALIZATION_VERSION}:[0-9a-f]{{64}}", BASE)


def test_deterministic() -> None:
    assert ast_hash(solution()) == BASE


@pytest.mark.parametrize(
    "code",
    [
        pytest.param(solution().replace("\n", "\n\n").replace("  ", "\t"), id="whitespace"),
        pytest.param(
            solution().replace(";\n", "; // комментарий\n").replace("begin", "/* блок */ begin"),
            id="comments",
        ),
        pytest.param(
            solution(word="data", acc="sum", inv="flip", i="k", block="g_bits", tap="bit_q"),
            id="internal-names",
        ),
        pytest.param(solution(mask="ALL_ONES"), id="localparam-name"),
        pytest.param(solution(acc="\\acc "), id="escaped-identifier"),
        pytest.param(solution(literal="8'd255"), id="decimal-literal"),
        pytest.param(solution(literal="8'b1111_1111"), id="binary-literal"),
        pytest.param(solution(literal="8'hff"), id="lower-case-hex"),
        pytest.param(solution(literal="8 'h F_F"), id="spaced-literal"),
        pytest.param(solution(literal="8'o377"), id="octal-literal"),
    ],
)
def test_same_hash(code: str) -> None:
    assert ast_hash(code) == BASE


@pytest.mark.parametrize(
    "code",
    [
        pytest.param(solution(literal="8'hFE"), id="literal-value"),
        pytest.param(solution(literal="255"), id="unsized-literal"),  # kept as written
        pytest.param(solution(literal="16'hFF"), id="literal-width"),
        pytest.param(solution().replace("(a & MASK)", "(MASK & a)"), id="operand-order"),
        pytest.param(
            solution().replace("assign y = inv(acc);", "always_comb y = inv(acc);"),
            id="assign-vs-always_comb",
        ),
        pytest.param(solution().replace("i < 2", "i < 3"), id="loop-bound"),
        pytest.param(solution().replace("    logic tap;", "    bit tap;"), id="keyword"),
    ],
)
def test_different_hash(code: str) -> None:
    assert code != solution()
    assert ast_hash(code) != BASE


def test_renaming_follows_first_appearance() -> None:
    # Two solutions that differ only by which name holds which value normalize alike.
    header = (
        "module top #(parameter int WIDTH = 8) (\n  input logic clk, input logic [WIDTH-1:0] a,"
    )
    header += " output logic [WIDTH-1:0] y\n);\n"
    first = (
        header
        + "  logic [7:0] p, q;\n  assign p = a;\n  assign q = ~p;\n  assign y = q;\nendmodule\n"
    )
    second = (
        header
        + "  logic [7:0] q, p;\n  assign q = a;\n  assign p = ~q;\n  assign y = p;\nendmodule\n"
    )
    assert ast_hash(first) == ast_hash(second)


def test_interface_names_are_kept() -> None:
    # Port and parameter names are part of the hash: they come from problem.yaml.
    keep = {"top", "clk", "a", "y", "WIDTH"}
    tokens = runner._tokens(syntax.SyntaxTree.fromText(solution()).root)
    stream = runner.normalize_tokens(tokens, keep)
    assert {"Identifier:clk", "Identifier:a", "Identifier:y", "Identifier:WIDTH"} <= set(stream)
    assert "Identifier:acc" not in stream
    assert "Identifier:_1" in stream


@pytest.mark.parametrize(
    ("base", "digits", "folded"),
    [
        ("'h", "FF", "'hff"),
        ("'d", "255", "'hff"),
        ("'b", "1111_1111", "'hff"),
        ("'o", "377", "'hff"),
        ("'sd", "5", "'sh5"),
        ("'SH", "a", "'sha"),
        ("'b", "10xZ", "'b10xz"),  # unknown digits are not folded
        ("'h", "?", "'h?"),
    ],
)
def test_based_literal(base: str, digits: str, folded: str) -> None:
    assert runner._based_literal(base, digits) == folded


def test_rejected_solution_has_no_hash() -> None:
    result = runner.precheck(solution().replace("assign y", "initial y = 0;\n  assign y"), JOB)
    assert result.findings
    assert result.ast_hash is None
