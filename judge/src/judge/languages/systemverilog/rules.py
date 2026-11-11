"""Rules of an SV package across its stages, checked by `judge validate` (specs/06 §2).

Synthesis metrics rank solutions only if the synthesized circuit passed the testbench too: every
`synth` of the submit pipeline is followed by a `sim` of its netlist (`netlist_sim`, specs/07 §2.5),
and a `sim` with `design` takes it from a `synth` that runs before it, at parameter sets the
`synth` has too (ADR-0014). The values of the parameter sets are number literals: they go into the
tool flags and scripts. `precheck` is not expanded: it checks the interface at every set itself.
"""

import re

from judge.core.package import Problem
from judge.languages.systemverilog.stages.precheck import PrecheckStage
from judge.languages.systemverilog.stages.sim import SimStage
from judge.languages.systemverilog.stages.synth import LITERAL, SynthStage

NETLIST_OUTPUT = "netlist_generic"


def package_rules(problem: Problem) -> list[str]:
    broken = [
        f"interface.param_sets {param_set.id}: {name} = {value!r} — не числовой литерал"
        for param_set in problem.interface.param_sets
        for name, value in param_set.values.items()
        if not re.match(LITERAL, str(value))
    ]
    broken += [
        f"этап {key}: precheck не раскрывается по наборам параметров — он сам сверяет интерфейс"
        " при каждом наборе; уберите param_sets"
        for key, stage in problem.stages.items()
        if stage.type == PrecheckStage.stage_type and stage.param_sets != "primary"
    ]
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
                continue
            missing = [
                s
                for s in problem.stage_param_sets(key)
                if s not in problem.stage_param_sets(source)
            ]
            if missing:
                broken.append(
                    f"этап {key}: наборы параметров {', '.join(missing)} — их нет у этапа"
                    f" {source}, нетлист для них не синтезируется"
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
