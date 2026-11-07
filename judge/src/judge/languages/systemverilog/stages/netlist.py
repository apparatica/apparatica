"""The design of `netlist_sim` (specs/07 §2.5): the netlist of `synth` under the problem `top`.

`synth` writes the netlist on Yosys internal gates as the module `<top>__netlist` without
parameters, synthesized with fixed values. The testbench instantiates `top` with parameters, so the
stage adds a wrapper `top` with the parameters and ports of `problem.yaml` around the netlist. The
wrapper stops elaboration with `$fatal` when the testbench sets a parameter to another value than
the netlist was synthesized with; the build turns that into an error with `-Werror-USERFATAL`
(S4). Such a mismatch is a problem bug, not the solution's.
"""

from collections.abc import Mapping

from judge.core.package import Port, Problem
from judge.core.stage import StageContext
from judge.languages.systemverilog.stages.synth import SynthConfig, SynthStage, synth_params

SUFFIX = "__netlist"  # the module name of the netlist is <top>__netlist (synth.yosys_script)


def wrapper(problem: Problem, params: Mapping[str, str]) -> str:
    """`top` with the parameters (defaults: the synthesized values) and ports of the interface,
    instantiating the netlist."""
    top = problem.top
    declared = ", ".join(
        f"parameter {p.type} {p.name} = {params[p.name]}" for p in problem.interface.parameters
    )
    header = f"module {top} #({declared}) (" if declared else f"module {top} ("
    ports = ",\n".join(f"  {_port(port)}" for port in problem.interface.ports)
    checks = [
        f"  if ({name} != {value}) begin : apx_check_{name}\n"
        f'    $fatal(1, "netlist synthesized for {name}={value}");\n'
        "  end"
        for name, value in params.items()
    ]
    connections = ", ".join(f".{port.name}({port.name})" for port in problem.interface.ports)
    return "\n".join(
        [
            "// Wrapper of netlist_sim: the testbench must use the synthesized parameters.",
            header,
            ports,
            ");",
            *checks,
            f"  {top}{SUFFIX} u ({connections});",
            "endmodule",
            "",
        ]
    )


def _port(port: Port) -> str:
    kind = "wire" if port.dir == "inout" else "logic"
    signed = " signed" if port.signed else ""
    return f"{port.dir} {kind}{signed} [({port.width})-1:0] {port.name}"


def netlist_design(ctx: StageContext, stage: str, netlist: bytes) -> bytes:
    """The netlist an earlier `synth` stage produced, with the wrapper for its parameters."""
    raw = ctx.problem.stages.get(stage)
    if raw is None or raw.type != SynthStage.stage_type:
        raise LookupError(
            f"stage {ctx.key}: design of {stage!r}: only a synth netlist is simulated"
        )
    config = SynthConfig.model_validate(raw.model_extra or {})
    params = synth_params(ctx.problem, config)
    return netlist.rstrip(b"\n") + b"\n\n" + wrapper(ctx.problem, params).encode()
