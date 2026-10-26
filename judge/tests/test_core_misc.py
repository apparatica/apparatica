import io
import json
from typing import Any

import pytest
from core_helpers import RESOURCE_CLASSES, make_problem
from pydantic import ValidationError

from judge.core import events, stage
from judge.core.limits import sandbox_limits, stage_limits
from judge.core.registry import UnknownLanguageError, get_language
from judge.core.verdict import aggregate


def result(key: str, status: str, ordinal: int = 0, **fields: Any) -> stage.StageResult:
    return stage.StageResult(key=key, type="t", ordinal=ordinal, status=status, **fields)  # type: ignore[arg-type]


WRONG = result("b", "failed", 1, failure_kind="wrong")
FAILED_TEST = stage.TestCase(id="t7", name="push и pop", group="public", status="failed", cycle=143)


@pytest.mark.parametrize(
    ("results", "cancelled", "status"),
    [
        ([result("a", "passed"), result("b", "passed", 1)], False, "accepted"),
        ([result("a", "warning"), result("b", "passed", 1)], False, "accepted_with_warnings"),
        ([result("a", "failed", failure_kind="forbidden")], False, "forbidden_construct"),
        ([result("a", "failed", failure_kind="compile")], False, "compile_error"),
        ([result("a", "failed", failure_kind="wrong")], False, "wrong_answer"),
        ([result("a", "failed", failure_kind="limit", limit="output")], False, "limit_exceeded"),
        ([result("a", "error", error_code="X"), WRONG], False, "internal_error"),
        ([result("a", "error", error_code="X")], True, "cancelled"),
        ([result("a", "cancelled"), result("b", "skipped", 1)], False, "cancelled"),
    ],
)  # fmt: skip
def test_verdict(results: list[stage.StageResult], cancelled: bool, status: str) -> None:
    assert aggregate(results, cancelled=cancelled).status == status


def test_first_failed_stage_in_pipeline_order_decides() -> None:
    summary = stage.StageSummary(tests=[FAILED_TEST])
    verdict = aggregate(
        [
            result("sim", "failed", 2, failure_kind="wrong", summary=summary),
            result("lint", "failed", 1, failure_kind="limit", limit="time"),
        ]
    )
    assert verdict.status == "limit_exceeded"
    assert verdict.detail.limit == "time"
    assert verdict.detail.first_failure is not None
    assert verdict.detail.first_failure.stage == "lint"


def test_verdict_detail() -> None:
    summary = stage.StageSummary(tests=[FAILED_TEST])
    detail = aggregate([result("sim", "failed", failure_kind="wrong", summary=summary)]).detail
    assert detail.first_failure is not None
    assert (detail.first_failure.test, detail.first_failure.cycle) == ("t7", 143)
    warned = aggregate([result("lint", "warning"), result("sim", "passed", 1)]).detail
    assert warned.warnings == ["lint"]
    errors = aggregate([result("sim", "error", error_code="OUTPUT_INVALID")]).detail
    assert errors.error_codes == ["OUTPUT_INVALID"]


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"status": "failed"}, "failure_kind"),
        ({"status": "passed", "failure_kind": "wrong"}, "failure_kind"),
        ({"status": "error"}, "error_code"),
        ({"status": "failed", "failure_kind": "wrong", "limit": "time"}, "limit"),
    ],
)
def test_outcome_consistency(fields: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        stage.StageOutcome(**fields)


def test_resource_class_defaults() -> None:
    problem = make_problem({"lint": {"type": "lint"}}, run=["lint"])
    limits = stage_limits(problem, "lint", "lint", RESOURCE_CLASSES)
    assert (limits.timeout_s, limits.output_bytes, limits.fst_bytes) == (10, 1 << 20, 16 << 20)
    other = stage_limits(problem, "lint", "custom", RESOURCE_CLASSES)
    assert other.timeout_s == RESOURCE_CLASSES.classes["light"].default_stage_timeout_s
    sandbox = sandbox_limits(problem, RESOURCE_CLASSES)
    assert (sandbox.cpus, sandbox.memory_mb, sandbox.pids) == (2, 2048, 256)


def test_problem_overrides_limits() -> None:
    problem = make_problem(
        {"sim_full": {"type": "sim"}},
        run=["sim_full"],
        limits={
            "stage_timeout_s": {"sim_full": 40},
            "memory_mb": 1024,
            "output_kb": 64,
            "fst_mb": 2,
        },
    )
    limits = stage_limits(problem, "sim_full", "sim", RESOURCE_CLASSES)
    assert (limits.timeout_s, limits.output_bytes, limits.fst_bytes) == (40, 64 << 10, 2 << 20)
    assert sandbox_limits(problem, RESOURCE_CLASSES).memory_mb == 1024


def test_timeout_override_is_bounded_by_the_class() -> None:
    problem = make_problem(
        {"sim": {"type": "sim"}}, run=["sim"], limits={"stage_timeout_s": {"sim": 3600}}
    )
    with pytest.raises(ValueError, match="exceeds 300"):
        stage_limits(problem, "sim", "sim", RESOURCE_CLASSES)


def test_registry_finds_systemverilog() -> None:
    assert get_language("systemverilog").name == "systemverilog"
    with pytest.raises(UnknownLanguageError, match="vhdl"):
        get_language("vhdl")


def test_jsonl_sink_round_trip() -> None:
    stream = io.BytesIO()
    sink = events.JsonlSink(stream)
    sink.emit(events.LogEvent(stage="lint", ch="err", text="ошибка"))
    sink.emit(events.StageEndEvent(result=result("lint", "passed")))
    lines = stream.getvalue().decode().splitlines()
    assert json.loads(lines[0]) == {"type": "log", "stage": "lint", "ch": "err", "text": "ошибка"}
    assert events.EVENT.validate_json(lines[1]) == events.StageEndEvent(
        result=result("lint", "passed")
    )


def test_console_sink() -> None:
    stream = io.StringIO()
    sink = events.ConsoleSink(stream)
    sink.emit(events.StageStartEvent(stage="sim", stage_type="sim", ordinal=2))
    sink.emit(events.LogEvent(stage="sim", ch="out", text="compiling"))
    sink.emit(events.HeartbeatEvent(stage="sim", elapsed_ms=3000, note="verilator"))
    sink.emit(events.TestEvent(stage="sim", test=FAILED_TEST))
    sink.emit(
        events.StageEndEvent(result=result("sim", "failed", failure_kind="wrong", duration_ms=1500))
    )
    lines = stream.getvalue().splitlines()
    assert lines[0].startswith("── sim ──")
    assert lines[1:] == [
        "compiling",
        "# sim: 3 s · verilator",
        "test t7 (push и pop): failed",
        "sim: failed (wrong, 1.5 s)",
    ]
