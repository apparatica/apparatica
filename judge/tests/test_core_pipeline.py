import io
import threading
from pathlib import Path

import pytest
from core_helpers import (
    FAKE,
    RESOURCE_CLASSES,
    ListSink,
    MemoryCache,
    cancel_after,
    make_problem,
)

from judge.core import events
from judge.core.executor import HostExecutor, OnLine
from judge.core.pipeline import CACHED_RUN_NOTE, Job, PipelineConfigError, run_pipeline
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


def test_build_cache_reaches_the_stages() -> None:
    cache = MemoryCache()
    problem = make_problem({"a": {"type": "cached"}}, ["a"])
    job = Job(problem, Path(), "run", seed=1, solution=b"")
    runs = []
    for _ in range(2):
        sink = ListSink()
        with HostExecutor() as executor:
            results = run_pipeline(job, FAKE, executor, sink, RESOURCE_CLASSES, build_cache=cache)
        notes = [e.text for e in sink.events if isinstance(e, events.LogEvent) and e.ch == "sys"]
        runs.append((results[0].cached, notes))
    assert runs == [(False, []), (True, ["from the cache: binary"])]


def run_twice(code: str, cache: MemoryCache) -> list[tuple[StageResult, list[tuple[str, str]]]]:
    """The same deterministic stage `a` and a stage `b` that reads its out.txt, run twice."""
    stages: dict[str, dict[str, object]] = {
        "a": {"type": "script", "code": code, "cache": True},
        "b": {"type": "script", "code": "assert open('from/a').read() == 'made'"},
    }
    problem = make_problem(stages, ["a", "b"])
    job = Job(problem, Path(), "run", seed=1, solution=b"module demo; endmodule\n")
    checks = []
    for _ in range(2):
        sink = ListSink()
        with HostExecutor() as executor:
            results = run_pipeline(job, FAKE, executor, sink, RESOURCE_CLASSES, build_cache=cache)
        assert results[1].status == "passed", "the files of the replayed run reach later stages"
        lines: list[tuple[str, str]] = [
            (e.ch, e.text) for e in sink.events if isinstance(e, events.LogEvent)
        ]
        checks.append((results[0], lines))
    return checks


def test_a_deterministic_plan_is_replayed_from_the_stage_cache(tmp_path: Path) -> None:
    counter = tmp_path / "runs"
    code = (
        f"open({str(counter)!r}, 'a').write('x'); print('measured'); "
        "open('out.txt', 'w').write('made')"
    )
    first, second = run_twice(code, MemoryCache())
    assert counter.read_text() == "x", "the second check does not run the plan"
    assert (first[0].cached, first[1]) == (False, [("out", "measured")])
    assert (second[0].cached, second[1]) == (True, [("sys", CACHED_RUN_NOTE), ("out", "measured")])
    assert first[0].metrics == second[0].metrics


def test_a_limit_is_not_kept_in_the_stage_cache() -> None:
    cache = MemoryCache()
    problem = make_problem(
        {"a": {"type": "script", "code": "print('x' * 2_000_000)", "cache": True}}, ["a"]
    )
    job = Job(problem, Path(), "run", seed=1, solution=b"")
    with HostExecutor() as executor:
        results = run_pipeline(job, FAKE, executor, ListSink(), RESOURCE_CLASSES, build_cache=cache)
    assert (results[0].failure_kind, results[0].limit) == ("limit", "output")
    assert not cache.files


def test_a_broken_stage_cache_entry_is_a_miss(tmp_path: Path) -> None:
    counter = tmp_path / "runs"
    code = f"open({str(counter)!r}, 'a').write('x'); open('out.txt', 'w').write('made')"
    cache = MemoryCache()
    run_twice(code, cache)
    cache.files = {key: b'{"version": 1, "files": "forged"}' for key in cache.files}
    run_twice(code, cache)
    assert counter.read_text() == "xx", "the forged entry is not used and is replaced"


# --- parameter sets (ADR-0014) -------------------------------------------------------------------

SETS_INTERFACE = {
    "parameters": [
        {"name": "WIDTH", "type": "int", "default": 8},
        {"name": "DEPTH", "type": "int", "default": 4},
    ],
    "param_sets": [
        {"id": "narrow", "values": {"WIDTH": 1}},
        {"id": "deep", "values": {"DEPTH": 16}},
    ],
    "ports": [{"name": "a", "dir": "input", "width": "WIDTH"}],
}
FAIL_AT_NARROW = "import sys; sys.exit(open('set.txt').read() == 'narrow')"


def run_sets(
    stages: dict[str, dict[str, object]],
    submit: list[str],
    *,
    keys: tuple[str, ...] | None = None,
    **extra: object,
) -> tuple[list[StageResult], ListSink]:
    stages = {"run": {"type": "script"}, **stages}  # Run checks the primary set only
    problem = make_problem(stages, run=["run"], submit=submit, interface=SETS_INTERFACE, **extra)
    sink = ListSink()
    job = Job(problem, Path(), "submit", seed=1, solution=b"", stages=keys)
    with HostExecutor() as executor:
        results = run_pipeline(job, FAKE, executor, sink, RESOURCE_CLASSES)
    return results, sink


def test_stages_expand_into_instances_by_stage_then_by_set() -> None:
    results, sink = run_sets(
        {
            "a": {"type": "set", "param_sets": "all"},
            "b": {"type": "set"},
            "c": {"type": "set", "param_sets": ["deep"]},
        },
        ["b", "a", "c"],
    )
    assert statuses(results) == [
        ("b", "passed"),
        ("a", "passed"),
        ("a@narrow", "passed"),
        ("a@deep", "passed"),
        ("c", "passed"),
        ("c@deep", "passed"),
    ]
    assert [r.ordinal for r in results] == [0, 1, 2, 3, 4, 5]
    assert [r.param_set.id if r.param_set else None for r in results] == [
        None, "default", "narrow", "deep", "default", "deep"
    ]  # fmt: skip
    narrow = results[2]
    assert narrow.param_set is not None
    assert narrow.param_set.values == {"WIDTH": 1, "DEPTH": 4}
    assert narrow.type == "set"
    # A stage gets its set and finds other stages at the same set; a stage at the primary set
    # only gets the primary set, and its result reports none.
    assert [(r.metrics["set"], r.metrics["a"]) for r in results] == [
        ("default", "a"),
        ("default", "a"),
        ("narrow", "a@narrow"),
        ("deep", "a@deep"),
        ("default", "a"),
        ("deep", "a@deep"),
    ]
    assert results[0].metrics["values"] == {"WIDTH": 8, "DEPTH": 4}
    starts = [e for e in sink.events if isinstance(e, events.StageStartEvent)]
    assert [(e.stage, e.param_set) for e in starts] == [(r.key, r.param_set) for r in results]


def test_a_failed_instance_skips_the_instances_after_it() -> None:
    results, _ = run_sets(
        {
            "a": {"type": "set", "param_sets": "all", "code": FAIL_AT_NARROW},
            "b": {"type": "set", "param_sets": "all"},
        },
        ["a", "b"],
    )
    assert statuses(results) == [
        ("a", "passed"),
        ("a@narrow", "failed"),
        ("a@deep", "skipped"),
        ("b", "skipped"),
        ("b@narrow", "skipped"),
        ("b@deep", "skipped"),
    ]
    assert results[2].param_set is not None
    assert results[2].param_set.id == "deep"
    assert results[2].summary.skip_reason == "previous_failed"


def test_the_timeout_of_a_stage_key_applies_to_every_instance() -> None:
    results, _ = run_sets(
        {"a": {"type": "set", "param_sets": ["narrow"]}},
        ["a"],
        limits={"stage_timeout_s": {"a": 7}},
    )
    assert [(r.key, r.metrics["timeout_s"]) for r in results] == [("a", 7), ("a@narrow", 7)]


def test_job_stages_name_instances() -> None:
    stages: dict[str, dict[str, object]] = {
        "a": {"type": "set", "param_sets": "all"},
        "b": {"type": "set", "param_sets": "all"},
    }
    results, _ = run_sets(stages, ["a", "b"], keys=("a", "a@narrow", "a@deep", "b", "b@narrow"))
    assert [r.key for r in results] == ["a", "a@narrow", "a@deep", "b", "b@narrow"]
    assert results[3].param_set is not None
    assert results[3].param_set.id == "default"


@pytest.mark.parametrize(
    ("key", "message"),
    [("z", "no stage 'z'"), ("a@wide", "has no set 'wide'"), ("b@narrow", "has no set 'narrow'")],
)
def test_job_stages_must_name_existing_instances(key: str, message: str) -> None:
    stages: dict[str, dict[str, object]] = {
        "a": {"type": "set", "param_sets": "all"},
        "b": {"type": "set"},
    }
    with pytest.raises(PipelineConfigError, match=message):
        run_sets(stages, ["a", "b"], keys=(key,))


def test_too_many_parameter_sets_do_not_run() -> None:
    interface = SETS_INTERFACE | {
        "param_sets": [{"id": f"s{n}", "values": {"WIDTH": n}} for n in range(1, 6)]
    }
    problem = make_problem({"a": {"type": "set"}}, run=["a"], interface=interface)
    job = Job(problem, Path(), "submit", seed=1, solution=b"")
    with (
        HostExecutor() as executor,
        pytest.raises(PipelineConfigError, match=r"5 extra .* allows \d+$"),
    ):
        run_pipeline(job, FAKE, executor, ListSink(), RESOURCE_CLASSES)


def test_the_console_names_the_set_of_an_instance() -> None:
    _, sink = run_sets(
        {"a": {"type": "set", "param_sets": ["narrow"]}, "b": {"type": "set"}}, ["a", "b"]
    )
    stream = io.StringIO()
    console = events.ConsoleSink(stream)
    for event in sink.events:
        if isinstance(event, events.StageStartEvent):
            console.emit(event)
    assert [line.rstrip("─ ") for line in stream.getvalue().splitlines()] == [
        "── a · WIDTH=8, DEPTH=4",
        "── a@narrow · WIDTH=1, DEPTH=4",
        "── b",
    ]
