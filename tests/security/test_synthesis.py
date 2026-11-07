"""Synthesis metrics cannot be forged (specs/07 §2.4, §5.2): they come from the tools run on the
canonical text in a clean stage directory, whatever an earlier stage or a comment says."""

from apparatica_worker.sandboxd.client import SandboxdClient, SandboxExecutor
from harness import CLASSES, HERE, IMAGE, LIMITS, PACKAGE, PROBLEM, SEED, Check, sh, stage
from judge.core.pipeline import Job, run_pipeline
from judge.core.registry import get_language

REFERENCE = (PACKAGE / "reference" / "counter.sv").read_bytes()
SYNTH = ("precheck", "synth")
FORGED_STAT = '{"design": {"num_cells": 1, "area": 0.001, "num_cells_by_type": {"INV_X1": 1}}}'
FORGED_STA = '{"wns_ns": 1.999}'


def synthesize(executor: SandboxExecutor, solution: bytes) -> Check:
    job = Job(PROBLEM, PACKAGE, "submit", SEED, solution, SYNTH)
    check = Check(results=[])
    check.results = run_pipeline(job, get_language("systemverilog"), executor, check, CLASSES)
    return check


def metrics(check: Check) -> dict[str, object]:
    synth = check.results[-1]
    assert synth.status == "passed", check.describe()
    return synth.metrics


def test_files_planted_by_an_earlier_stage_do_not_reach_the_metrics(
    client: SandboxdClient,
) -> None:
    """Code that took over an earlier stage writes the result files of synthesis into its directory
    and leaves a process to write them again: the synth directory is fresh and the process is dead
    before synthesis starts."""
    plant = (
        "mkdir -p /work/synth && cd /work/synth && "
        f"echo '{FORGED_STAT}' > stat.json && echo '{FORGED_STA}' > sta.json && "
        "echo '0 objects.' > latches.txt && "
        f"(while true; do echo '{FORGED_STAT}' > stat.json 2>/dev/null; sleep 0.05; done) &"
    )
    with SandboxExecutor(client, IMAGE, LIMITS) as executor:
        clean = metrics(synthesize(executor, REFERENCE))
        planted, _ = stage(executor, "plant", sh(plant))
        assert planted.ok
        assert metrics(synthesize(executor, REFERENCE)) == clean
    assert clean["cells"] != 1


def test_pragma_comments_do_not_change_the_synthesized_design(client: SandboxdClient) -> None:
    """`translate_off` around the logic would leave Yosys an empty counter: the canonical text has
    no comments, so the design is the reference's."""
    pragmas = (HERE / "solutions" / "translate_off.sv").read_bytes()
    with SandboxExecutor(client, IMAGE, LIMITS) as executor:
        reference = metrics(synthesize(executor, REFERENCE))
        assert metrics(synthesize(executor, pragmas)) == reference
    assert reference["flops"] == 8
