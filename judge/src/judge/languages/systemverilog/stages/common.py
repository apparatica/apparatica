"""What the SystemVerilog stages share."""

import re

from judge.core.stage import ParamSet, StageContext

SOLUTION = "solution.sv"

# A parameter value goes into the tool scripts and flags: a number literal only, no spaces or
# separators (the package rules check the defaults and the values of the parameter sets, rules.py).
LITERAL = r"^-?[0-9][0-9_]*$|^[0-9]*'[sS]?[bBoOdDhH][0-9a-fA-FxXzZ?_]+$"


def canonical_solution(ctx: StageContext) -> bytes:
    """The canonical text from precheck: later stages never see the user's original code."""
    for finished in reversed(list(ctx.previous.values())):
        if SOLUTION in finished.outputs:
            return finished.outputs[SOLUTION]
    raise LookupError(f"stage {ctx.key} needs a precheck stage before it (specs/07 §2.1)")


def param_values(param_set: ParamSet) -> dict[str, str]:
    """Every parameter of the interface with its value at the set of the stage instance
    (ADR-0014), as the tools get it: `-G` of Verilator and of `read_slang`, the netlist wrapper."""
    values = {name: str(value) for name, value in param_set.values.items()}
    for name, value in values.items():
        if not re.match(LITERAL, value):
            raise ValueError(f"parameter {name}: {value!r} is not a literal")
    return values
