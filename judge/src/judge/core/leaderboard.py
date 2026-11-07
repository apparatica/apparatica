"""Which Submit may enter the leaderboard of its problem (FR-LB-02, FR-JDG-13, ADR-0006).

The judge's part of the condition: every stage of the submit pipeline passed (with warnings or
not) — a missing result is not a pass — and every metric of `leaderboard.order` is a number. The
pipeline of a package with synthesis includes the simulation of its netlist (`judge validate`
checks the language rules), so a solution whose netlist behaves differently from its code is not
ranked. The ingestor adds what the judge does not know: a signed-in author, the current epoch and
the default toolchain profile.
"""

from collections.abc import Sequence

from judge.core.package import Problem
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
