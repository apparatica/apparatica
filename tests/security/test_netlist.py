"""A circuit that behaves differently from its code does not rank (specs/07 §2.5, specs/09 §4.2).

The suite cannot write a solution that passes the RTL simulation but not its own netlist (S4 found
none), so it stands one in: the synthesis of the reference with one operator of the netlist
replaced, as Yosys would give for code that synthesis and simulation read differently.
"""

import dataclasses
import re
from collections.abc import Sequence

from apparatica_worker.sandboxd.client import SandboxdClient, SandboxExecutor
from harness import CLASSES, IMAGE, LIMITS, PACKAGE, PROBLEM, SEED, Check
from judge.core.leaderboard import leaderboard_metrics
from judge.core.pipeline import Job, run_pipeline
from judge.core.registry import LanguageModule, get_language
from judge.core.stage import ExecResult, StageContext, StageOutcome
from judge.languages.systemverilog.stages.synth import SynthStage

REFERENCE = (PACKAGE / "reference" / "counter.sv").read_bytes()
# The first gate of the netlist with two inputs: `&` → `|`.
GATE = re.compile(rb"(assign [^;]*?) & ")


class ForgedSynth(SynthStage):
    def interpret(self, ctx: StageContext, runs: Sequence[ExecResult]) -> StageOutcome:
        outcome = super().interpret(ctx, runs)
        netlist = outcome.outputs["netlist_generic"]
        forged, replaced = GATE.subn(rb"\1 | ", netlist, count=1)
        assert replaced == 1, netlist.decode()
        return outcome.model_copy(update={"outputs": {"netlist_generic": forged}})


def submit(client: SandboxdClient, language: LanguageModule) -> Check:
    job = Job(PROBLEM, PACKAGE, "submit", SEED, REFERENCE)
    check = Check(results=[])
    with SandboxExecutor(client, IMAGE, LIMITS) as executor:
        check.results = run_pipeline(job, language, executor, check, CLASSES)
    return check


def test_the_netlist_of_the_reference_ranks_it(client: SandboxdClient) -> None:
    check = submit(client, get_language("systemverilog"))
    assert check.verdict.status == "accepted", check.describe()
    assert leaderboard_metrics(PROBLEM, check.results) is not None


def test_a_netlist_unlike_the_code_is_a_wrong_answer_and_does_not_rank(
    client: SandboxdClient,
) -> None:
    real = get_language("systemverilog")
    forged = dataclasses.replace(real, stages={**real.stages, "synth": ForgedSynth})
    check = submit(client, forged)
    why = check.describe()
    statuses = {r.key: r.status for r in check.results}
    assert (statuses["sim_full"], statuses["synth"]) == ("passed", "passed"), why
    assert check.verdict.status == "wrong_answer", why
    first = check.verdict.detail.first_failure
    assert first is not None, why
    assert first.stage == "netlist_sim", why
    netlist_sim = check.results[-1]
    assert netlist_sim.summary.caption is not None, why
    assert netlist_sim.summary.caption.startswith("синтезированная схема ведёт себя иначе"), why
    assert leaderboard_metrics(PROBLEM, check.results) is None
