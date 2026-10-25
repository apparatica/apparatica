"""What the SystemVerilog stages share."""

from judge.core.stage import StageContext

SOLUTION = "solution.sv"


def canonical_solution(ctx: StageContext) -> bytes:
    """The canonical text from precheck: later stages never see the user's original code."""
    for finished in reversed(list(ctx.previous.values())):
        if SOLUTION in finished.outputs:
            return finished.outputs[SOLUTION]
    raise LookupError(f"stage {ctx.key} needs a precheck stage before it (specs/07 §2.1)")
