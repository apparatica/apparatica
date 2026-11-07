"""Rules of an SV package across its stages, checked by `judge validate` (specs/06 §2).

Synthesis metrics rank solutions only if the synthesized circuit passed the testbench too: every
`synth` of the submit pipeline is followed by a `sim` of its netlist (`netlist_sim`, specs/07 §2.5),
and a `sim` with `design` takes it from a `synth` that runs before it.
"""

from judge.core.package import Problem
from judge.languages.systemverilog.stages.sim import SimStage
from judge.languages.systemverilog.stages.synth import SynthStage

NETLIST_OUTPUT = "netlist_generic"


def package_rules(problem: Problem) -> list[str]:
    broken = []
    practice = problem.pipelines.practice
    for name, keys in (("run", practice.run), ("submit", practice.submit)):
        for index, key in enumerate(keys):
            design = _design(problem, key)
            if design is None:
                continue
            source, _, output = design.partition(".")
            earlier = keys[:index]
            if (
                source not in earlier
                or problem.stages[source].type != SynthStage.stage_type
                or output != NETLIST_OUTPUT
            ):
                broken.append(
                    f"этап {key}: design {design} — нужен {NETLIST_OUTPUT} этапа synth, который"
                    f" идёт раньше в pipelines.practice.{name}"
                )
        if name != "submit":
            continue
        for index, key in enumerate(keys):
            if problem.stages[key].type != SynthStage.stage_type:
                continue
            wanted = f"{key}.{NETLIST_OUTPUT}"
            if not any(_design(problem, later) == wanted for later in keys[index + 1 :]):
                broken.append(
                    f"этап {key}: после синтеза нужна симуляция нетлиста — этап"
                    f" {{type: sim, design: {wanted}}} в pipelines.practice.submit"
                )
    return broken


def _design(problem: Problem, key: str) -> str | None:
    stage = problem.stages[key]
    if stage.type != SimStage.stage_type:
        return None
    design = (stage.model_extra or {}).get("design")
    return design if isinstance(design, str) else None
