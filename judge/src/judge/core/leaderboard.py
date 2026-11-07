"""Which Submit may enter the leaderboard of its problem (FR-LB-02, FR-JDG-13, ADR-0006).

The judge's part of the condition: every stage of the submit pipeline passed (with warnings or
not) — a missing result is not a pass — and every metric of `leaderboard.order` is a number. The
pipeline of a package with synthesis includes the simulation of its netlist (`judge validate`
checks the language rules), so a solution whose netlist behaves differently from its code is not
ranked. The ingestor adds what the judge does not know: a signed-in author, the current epoch and
the default toolchain profile.

The place compares `sort_values`: the metrics in the order of the formula, negated where a larger
value ranks higher, so that every key sorts ascending (ADR-0006).
"""

from collections.abc import Sequence

from judge.core.package import Leaderboard, Problem
from judge.core.stage import StageResult

PASSED = ("passed", "warning")


def leaderboard_metrics(
    problem: Problem, results: Sequence[StageResult]
) -> dict[str, float] | None:
    """The metrics of the formula, `<stage key>.<metric>` → value, if the Submit is ranked; None
    if the problem has no leaderboard or the Submit may not enter it."""
    if problem.leaderboard is None:
        return None
    by_key = {result.key: result for result in results}
    for key in problem.pipelines.practice.submit:
        result = by_key.get(key)
        if result is None or result.status not in PASSED:
            return None
    values = {}
    for item in problem.leaderboard.order:
        stage, metric = item.metric.split(".", 1)
        value = by_key[stage].metrics.get(metric)  # the stages of the formula are in submit
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        values[item.metric] = float(value)
    return values


def sort_values(leaderboard: Leaderboard, metrics: dict[str, float]) -> list[float]:
    """What the place is compared by: the metrics in the order of the formula, ascending."""
    return [
        metrics[item.metric] if item.dir == "asc" else -metrics[item.metric]
        for item in leaderboard.order
    ]


def ast_hash(results: Sequence[StageResult]) -> str | None:
    """The hash of the normalized syntax tree that groups equal solutions (FR-LB-04): the metric
    `ast_hash` of the stage of the language that reports it (`precheck/v1` in SystemVerilog)."""
    for result in results:
        value = result.metrics.get("ast_hash")
        if isinstance(value, str):
            return value
    return None
