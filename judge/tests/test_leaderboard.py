"""Which Submit may enter the leaderboard (FR-LB-02, FR-JDG-13)."""

from pathlib import Path
from typing import Any

import pytest

from judge.core.leaderboard import leaderboard_metrics
from judge.core.package import load_manifest
from judge.core.stage import StageResult

FIFO = load_manifest(Path(__file__).parent / "data" / "sync-fifo")
SUBMIT = FIFO.pipelines.practice.submit  # precheck, lint, sim_full, synth, netlist_sim, formal
SYNTH = {"critical_path_ns": 0.5917, "area_um2": 1194, "cells": 526}


def results(**changes: Any) -> list[StageResult]:
    """Every stage of submit passed; a change is a status, a dict of metrics or None (missing)."""
    found = []
    for ordinal, key in enumerate(SUBMIT):
        change = changes.get(key, "passed")
        if change is None:
            continue
        metrics = SYNTH if key == "synth" else {}
        if isinstance(change, dict):
            metrics, change = change, "passed"
        status_fields: dict[str, Any] = {"status": change}
        if change == "failed":
            status_fields["failure_kind"] = "wrong"
        found.append(
            StageResult(key=key, type=key, ordinal=ordinal, metrics=metrics, **status_fields)
        )
    return found


def test_an_accepted_submit_ranks_with_the_metrics_of_the_formula() -> None:
    assert leaderboard_metrics(FIFO, results()) == {
        "synth.critical_path_ns": 0.5917,
        "synth.area_um2": 1194.0,
    }
    assert leaderboard_metrics(FIFO, results(lint="warning")) is not None


@pytest.mark.parametrize(
    "changes",
    [
        {"netlist_sim": "failed"},
        {"netlist_sim": None},
        {"netlist_sim": "skipped"},
        {"formal": "error"},
        {"synth": {"critical_path_ns": 0.5}},
        {"synth": {"critical_path_ns": 0.5, "area_um2": "1194"}},
        {"synth": {"critical_path_ns": 0.5, "area_um2": True}},
    ],
    ids=[
        "netlist-differs",
        "no-netlist-sim",
        "netlist-sim-skipped",
        "a-stage-error",
        "metric-missing",
        "metric-not-a-number",
        "metric-a-bool",
    ],
)
def test_a_submit_that_may_not_rank(changes: dict[str, Any]) -> None:
    assert leaderboard_metrics(FIFO, results(**changes)) is None


def test_a_problem_without_a_leaderboard() -> None:
    problem = FIFO.model_copy(update={"leaderboard": None})
    assert leaderboard_metrics(problem, results()) is None
