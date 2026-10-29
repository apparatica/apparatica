import threading
from pathlib import Path

import pytest
from core_helpers import FAKE, RESOURCE_CLASSES, ListSink, cancel_after, make_problem

from judge.core import events
from judge.core.executor import HostExecutor, OnLine
from judge.core.pipeline import Job, PipelineConfigError, run_pipeline
from judge.core.stage import ExecResult, StagePlan, StageResult


def run(
    stages: dict[str, dict[str, object]],
    order: list[str],
    *,
    cancel_s: float | None = None,
) -> tuple[list[StageResult], ListSink]:
    problem = make_problem(stages, run=order)
    sink = ListSink()
    job = Job(problem, Path(), "run", seed=41917, solution=b"module demo; endmodule\n")
    cancel = cancel_after(cancel_s) if cancel_s is not None else None
    with HostExecutor() as executor:
        results = run_pipeline(job, FAKE, executor, sink, RESOURCE_CLASSES, cancel)
    return results, sink


def statuses(results: list[StageResult]) -> list[tuple[str, str]]:
    return [(r.key, r.status) for r in results]


def test_all_stages_pass_and_pass_files_on() -> None:
    write = "open('out.txt', 'w').write(open('solution.sv').read().upper())"
    read = "print(open('from/a').read(), end='')"
    results, sink = run(
        {"a": {"type": "script", "code": write}, "b": {"type": "script", "code": read}},
        ["a", "b"],
    )
    assert statuses(results) == [("a", "passed"), ("b", "passed")]
    assert results[0].metrics == {"runs": 1}
    assert results[0].metrics_schema == "script/v1"
    assert results[0].duration_ms is not None
    assert results[0].started_at is not None
    logs = [e.text for e in sink.events if isinstance(e, events.LogEvent) and e.stage == "b"]
    assert logs == ["MODULE DEMO; ENDMODULE"]
    assert [e.type for e in sink.events] == [
        "stage_start",
        "stage_end",
        "stage_start",
        "log",
        "stage_end",
        "done",
    ]


def test_failure_skips_the_rest() -> None:
    results, _ = run(
        {
            "a": {"type": "script", "code": "raise SystemExit(1)"},
            "b": {"type": "script"},
            "c": {"type": "script"},
        },
        ["a", "b", "c"],
    )
    assert statuses(results) == [("a", "failed"), ("b", "skipped"), ("c", "skipped")]
    assert results[0].failure_kind == "wrong"
    assert results[1].summary.skip_reason == "previous_failed"
    assert results[1].ordinal == 1


def test_warning_does_not_stop_the_pipeline() -> None:
    results, _ = run({"a": {"type": "script", "warn": True}, "b": {"type": "script"}}, ["a", "b"])
    assert statuses(results) == [("a", "warning"), ("b", "passed")]


def test_submit_pipeline_is_used_for_submit() -> None:
    problem = make_problem(
        {"a": {"type": "script"}, "b": {"type": "script"}}, run=["a"], submit=["a", "b"]
    )
    job = Job(problem, Path(), "submit", seed=1, solution=b"")
    with HostExecutor() as executor:
        results = run_pipeline(job, FAKE, executor, ListSink(), RESOURCE_CLASSES)
    assert [r.key for r in results] == ["a", "b"]


def test_progress_lines_become_test_events() -> None:
    code = "print('@@test t1'); print('plain')"
    _, sink = run({"a": {"type": "script", "code": code}}, ["a"])
    tests = [e.test.id for e in sink.events if isinstance(e, events.TestEvent)]
    logs = [e.text for e in sink.events if isinstance(e, events.LogEvent)]
    assert tests == ["t1"]
    assert logs == ["plain"]


def test_output_limit_reports_truncation() -> None:
    results, sink = run(
        {"a": {"type": "script", "code": "while True: print('y' * 1000)"}},
        ["a"],
    )
    assert (results[0].status, results[0].failure_kind, results[0].limit) == (
        "failed",
        "limit",
        "output",
    )
    truncated = [e for e in sink.events if isinstance(e, events.TruncatedEvent)]
    assert [t.limit_kb for t in truncated] == [1024]


def test_follow_up_run() -> None:
    code = "open('left.txt', 'w').write('kept'); raise SystemExit(1)"
    results, sink = run({"a": {"type": "retry", "code": code}}, ["a"])
    assert statuses(results) == [("a", "passed")]
    assert results[0].metrics == {"runs": 2}
    assert [e.text for e in sink.events if isinstance(e, events.LogEvent)] == ["kept"]


def test_artifacts_go_to_the_artifact_sink_not_to_later_stages() -> None:
    kept: list[tuple[str, str, bytes]] = []
    problem = make_problem(
        {
            "a": {"type": "artifact", "code": "open('out.txt', 'w').write('fst')"},
            "b": {"type": "script", "code": "import os; print(os.path.exists('from/a'))"},
        },
        run=["a", "b"],
    )
    sink = ListSink()
    job = Job(problem, Path(), "run", seed=1, solution=b"")
    with HostExecutor() as executor:
        run_pipeline(
            job,
            FAKE,
            executor,
            sink,
            RESOURCE_CLASSES,
            on_artifact=lambda *item: kept.append(item),
        )
    assert kept == [("a", "out.txt", b"fst")]
    assert [e.text for e in sink.events if isinstance(e, events.LogEvent)] == ["False"]


def test_endless_follow_ups_are_an_error() -> None:
    results, _ = run({"a": {"type": "loop"}, "b": {"type": "script"}}, ["a", "b"])
    assert statuses(results) == [("a", "error"), ("b", "skipped")]
    assert results[0].error_code == "STAGE_RUNS_EXCEEDED"


def test_plugin_crash_is_an_error() -> None:
    results, sink = run({"a": {"type": "crash"}}, ["a"])
    assert results[0].status == "error"
    assert results[0].error_code == "STAGE_CRASHED"
    sys_logs = [e.text for e in sink.events if isinstance(e, events.LogEvent) and e.ch == "sys"]
    assert "plugin bug" in sys_logs[0]


def test_executor_failure_is_an_error() -> None:
    results, _ = run({"a": {"type": "missing"}}, ["a"])
    assert (results[0].status, results[0].error_code) == ("error", "EXECUTOR_FAILED")


def test_cancellation_during_a_stage() -> None:
    results, _ = run(
        {"a": {"type": "script", "code": "import time; time.sleep(30)"}, "b": {"type": "script"}},
        ["a", "b"],
        cancel_s=0.3,
    )
    assert statuses(results) == [("a", "cancelled"), ("b", "skipped")]
    assert results[1].summary.skip_reason == "cancelled"


def test_the_console_says_why_a_stage_was_cancelled() -> None:
    problem = make_problem({"a": {"type": "script", "code": "import time; time.sleep(30)"}}, ["a"])
    job = Job(problem, Path(), "run", seed=1, solution=b"module demo; endmodule\n")
    sink = ListSink()
    with HostExecutor() as executor:
        run_pipeline(
            job,
            FAKE,
            executor,
            sink,
            RESOURCE_CLASSES,
            cancel_after(0.3),
            cancel_note=lambda: "cancelled by the user",
        )
    notes = [e.text for e in sink.events if isinstance(e, events.LogEvent) and e.ch == "sys"]
    assert notes[-1] == "cancelled by the user"


def test_stage_config_is_validated_before_running() -> None:
    with pytest.raises(PipelineConfigError, match="stage a"):
        run({"a": {"type": "script", "unknown": 1}}, ["a"])


def test_unknown_stage_type() -> None:
    with pytest.raises(PipelineConfigError, match="no stage type 'synth'"):
        run({"a": {"type": "synth"}}, ["a"])


def test_problem_timeout_override_applies() -> None:
    problem = make_problem(
        {"a": {"type": "script", "code": "import time; time.sleep(30)"}},
        run=["a"],
        limits={"stage_timeout_s": {"a": 0.5}},
    )
    job = Job(problem, Path(), "run", seed=1, solution=b"")
    with HostExecutor() as executor:
        results = run_pipeline(job, FAKE, executor, ListSink(), RESOURCE_CLASSES)
    assert (results[0].failure_kind, results[0].limit) == ("limit", "time")


class OutOfMemoryExecutor(HostExecutor):
    """Every run ends as a sandbox that its memory limit killed (gVisor)."""

    def run(
        self,
        stage_key: str,
        plan: StagePlan,
        on_line: OnLine,
        cancel: threading.Event,
        *,
        reuse_dir: bool = False,
    ) -> ExecResult:
        return ExecResult(commands=(), output="", memory_exceeded=True)


def test_a_sandbox_out_of_memory_is_the_memory_limit() -> None:
    problem = make_problem({"a": {"type": "script"}, "b": {"type": "script"}}, run=["a", "b"])
    job = Job(problem, Path(), "run", seed=1, solution=b"module demo; endmodule\n")
    with OutOfMemoryExecutor() as executor:
        results = run_pipeline(job, FAKE, executor, ListSink(), RESOURCE_CLASSES)
    assert statuses(results) == [("a", "failed"), ("b", "skipped")]
    assert (results[0].failure_kind, results[0].limit) == ("limit", "memory")
