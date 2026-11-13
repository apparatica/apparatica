import pytest

from measure_submit import Round, p50, p95, report, round_of, vary


def test_vary_adds_a_line_of_whitespace_only() -> None:
    code = "module top;\nendmodule\n"
    first, second = vary(code, 1), vary(code, 2)
    assert first != second
    for varied in (first, second):
        line, rest = varied.split("\n", 1)
        assert rest == code
        assert len(line) == 64
        assert set(line) == {" ", "\t"}


def stage(key: str, ms: int | None, set_id: str | None = None) -> dict[str, object]:
    param_set = None if set_id is None else {"id": set_id, "values": {}}
    return {"key": key, "duration_ms": ms, "param_set": param_set}


SUBMISSION = {
    "created_at": "2026-11-13T10:00:00+00:00",
    "started_at": "2026-11-13T10:00:01.500000+00:00",
    "finished_at": "2026-11-13T10:00:21.500000+00:00",
    "stages": [
        stage("precheck", 400),
        stage("lint", 600),
        stage("sim_full", 3000, "default"),
        stage("sim_full@narrow", 2500, "narrow"),
        stage("synth", 5000, "default"),
        stage("synth@narrow", 4000, "narrow"),
        stage("netlist_sim", None, "default"),  # never started: no duration
    ],
}


def test_round_of_splits_the_time_by_stage_and_set() -> None:
    measured = round_of(SUBMISSION, wall_s=21.0)
    assert measured.check_s == 20.0
    assert measured.queue_s == 1.5
    assert measured.stages_s == {
        "precheck": 0.4,
        "lint": 0.6,
        "sim_full": 5.5,
        "synth": 9.0,
        "netlist_sim": 0.0,
    }
    # stages without a set (precheck, lint) belong to the primary one
    assert measured.sets_s == pytest.approx({"default": 9.0, "narrow": 6.5})


def test_percentiles() -> None:
    values = [float(n) for n in range(1, 21)]
    assert p50(values) == 10.5
    assert p95(values) == pytest.approx(19.05)
    assert p95([7.0]) == 7.0


def test_report_orders_stages_by_time() -> None:
    rounds = [round_of(SUBMISSION, 21.0), Round(10.0, 0.0, 11.0, {"synth": 1.0}, {"default": 1.0})]
    lines = report(rounds)
    assert lines[1].split()[-3:] == ["15.00", "19.50", "20.00"]  # check: p50, p95, max
    stages = [line.split()[0] for line in lines[lines.index("by stage (all instances)") + 1 :]][:5]
    assert stages == ["synth", "sim_full", "lint", "precheck", "netlist_sim"]
