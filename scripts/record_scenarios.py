"""Record the submission scenarios of the frontend mocks from real checks (specs/05 §0, T1.0).

Each scenario judges a solution of a demo problem in the toolchain image and writes
web/src/mocks/scenarios/<name>.json: the submission as `GET /submissions/{id}` shows it after the
check, the events of `GET /submissions/{id}/events` and the FST trace, if any. The pipeline events
get what the worker, the API and the ingestor add to them (specs/07 §4.1): the attempt, log lines
glued for 75 ms, heartbeats on silent steps, the queue position before and the final status after.
An event id is a Valkey stream id, milliseconds since the epoch: the mocks replay the timing.

    poetry -C judge run python ../scripts/record_scenarios.py [--image IMAGE] [name ...]

Stand-ins of checks at several parameter sets are put together from these recordings after every
run, without the toolchain (`stand_ins`): name only stand-ins to rewrite just them.

A backend test checks the files against the API schemas (backend/tests/test_mock_scenarios.py).
"""

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, Self

from judge.core.events import Event, LogEvent, StageEndEvent, StageStartEvent
from judge.core.executor import Executor, ExecutorError, LocalDockerExecutor, OnLine
from judge.core.limits import ResourceClasses, load_resource_classes, sandbox_limits
from judge.core.package import load_manifest
from judge.core.pipeline import Job, run_pipeline
from judge.core.registry import get_language
from judge.core.stage import (
    ExecResult,
    HiddenTests,
    ParamSet,
    StagePlan,
    StageResult,
    StageSummary,
)
from judge.core.verdict import Verdict, aggregate

ROOT = Path(__file__).resolve().parents[1]
PROBLEMS = ROOT / "problems"
OUTPUT = ROOT / "web" / "src" / "mocks" / "scenarios"
RESOURCE_CLASSES = ROOT / "config" / "resource-classes.yaml"
DEFAULT_IMAGE = "apparatica-toolchain:dev"
PROFILE = "sv-dev"
SEED = 20261026  # one seed for all recordings: a new recording keeps the verdicts

GLUE_MS = 75  # the worker glues log lines for this long (specs/07 §4.1) ...
GLUE_BYTES = 8 << 10  # ... or up to this size
HEARTBEAT_MS = 1000  # a silent stage sends a heartbeat this often
QUEUE = ((0, 2, 4), (600, 1, 2))  # (ms, position, eta_s): what the API sends while queued
STARTED_MS = 1200  # the worker takes the check
FINALIZED_MS = 120  # the ingestor stores the result after `done`

Kind = Literal["run", "submit"]
Timed = tuple[int, dict[str, Any]]  # ms since the submission was created, the event


@dataclass(frozen=True)
class Scenario:
    problem: str
    kind: Kind
    solution: Callable[[Path], str]  # the code, from the package directory
    cancel: tuple[str, float] | None = None  # cancel this many seconds after the stage started
    broken_stage: str | None = None  # the executor fails on this stage: a platform failure
    retry_after: str | None = None  # the first attempt dies after this stage
    output_kb: int | None = None  # a lower output limit keeps the file of the scenario small


def reference(package: Path) -> str:
    return next((package / "reference").glob("*.sv")).read_text(encoding="utf-8")


def mutant(name: str) -> Callable[[Path], str]:
    return lambda package: (package / "mutants" / name).read_text(encoding="utf-8")


def edited(old: str, new: str) -> Callable[[Path], str]:
    def solution(package: Path) -> str:
        code = reference(package)
        if code.count(old) != 1:
            raise ValueError(f"{old!r} is not in the reference of {package.name} exactly once")
        return code.replace(old, new)

    return solution


SCENARIOS = {
    "run-passed": Scenario("mux4", "run", reference),
    "accepted": Scenario("sync-fifo", "submit", reference),
    "accepted-with-warnings": Scenario("mux4", "submit", edited("y = d0;", "y = {1'b0, d0};")),
    "wrong-answer": Scenario("sync-fifo", "run", mutant("m01_full_off_by_one.sv")),
    "wrong-answer-hidden": Scenario("counter-mod-n", "submit", mutant("m02_wrap_without_en.sv")),
    "compile-error": Scenario("mux4", "run", edited("y = d3;", "y = d3")),
    "forbidden-construct": Scenario("counter-mod-n", "run", mutant("m05_delay.sv")),
    "output-limit": Scenario(
        "sync-fifo",
        "run",
        output_kb=16,
        solution=edited(
            "endmodule",
            "  always_ff @(posedge clk)\n"
            '    for (int i = 0; i < 1000; i++) $display("count=%0d", count);\n'
            "endmodule",
        ),
    ),
    "cancelled": Scenario("sync-fifo", "run", reference, cancel=("sim_run", 2.0)),
    "internal-error": Scenario("mux4", "run", reference, broken_stage="sim_run"),
    "retry": Scenario("mux4", "run", reference, retry_after="lint"),
}


# --- what the worker, the API and the ingestor add to the pipeline events ----------------------


def worker_events(recorded: Sequence[tuple[int, Event]], attempt: int) -> list[Timed]:
    """Pipeline events as the worker sends them: with the attempt, log lines glued, heartbeats."""
    glued: list[Timed] = []
    pending: tuple[int, LogEvent, list[str]] | None = None

    def flush() -> None:
        nonlocal pending
        if pending is not None:
            ms, first, lines = pending
            text = "".join(line + "\n" for line in lines)
            glued.append((ms, {"type": "log", "stage": first.stage, "ch": first.ch, "text": text}))
            pending = None

    for ms, event in recorded:
        if isinstance(event, LogEvent):
            if (
                pending is not None
                and (pending[1].stage, pending[1].ch) == (event.stage, event.ch)
                and ms - pending[0] <= GLUE_MS
                and sum(len(line) + 1 for line in pending[2]) + len(event.text) < GLUE_BYTES
            ):
                pending[2].append(event.text)
                continue
            flush()
            pending = (ms, event, [event.text])
            continue
        flush()
        glued.append((ms, event.model_dump(mode="json")))
    flush()

    events: list[Timed] = []
    stage: tuple[str, int] | None = None  # the running stage and its start
    for ms, data in glued:
        if stage is not None and events:
            beat = events[-1][0] + HEARTBEAT_MS
            while beat < ms:
                elapsed = beat - stage[1]
                heartbeat = {
                    "type": "heartbeat",
                    "stage": stage[0],
                    "elapsed_ms": elapsed,
                    "note": None,
                }
                events.append((beat, heartbeat))
                beat += HEARTBEAT_MS
        if data["type"] == "stage_start":
            stage = (data["stage"], ms)
        elif data["type"] == "stage_end":
            stage = None
        events.append((ms, data))
    return [(ms, data | {"attempt": attempt}) for ms, data in events]


def timeline(attempts: Sequence[list[Timed]], verdict: Verdict) -> list[Timed]:
    """The whole stream: the queue, the attempts of the worker, the final status."""
    events: list[Timed] = [
        (ms, {"type": "queue", "position": position, "eta_s": eta}) for ms, position, eta in QUEUE
    ]
    for attempt in attempts:
        events += attempt
    events.append(
        (
            events[-1][0] + FINALIZED_MS,
            {
                "type": "finalized",
                "status": verdict.status,
                "verdict_detail": verdict.detail.model_dump(mode="json"),
                "leaderboard": None,  # the mocks place a signed-in author (leaderboards.ts)
            },
        )
    )
    return events


def stream_ids(created_ms: int, events: Sequence[Timed]) -> list[dict[str, Any]]:
    """SSE events with Valkey stream ids: `<ms>-<seq>`, the sequence numbers one millisecond."""
    numbered = []
    previous, seq = -1, 0
    for ms, data in events:
        at = max(created_ms + ms, previous)
        seq = seq + 1 if at == previous else 0
        numbered.append({"id": f"{at}-{seq}", "event": data})
        previous = at
    return numbered


# --- recording --------------------------------------------------------------------------------


class _Recorder:
    """Pipeline events with the milliseconds since the check started."""

    def __init__(self, on_event: Callable[[Event], None]) -> None:
        self.events: list[tuple[int, Event]] = []
        self._start = time.monotonic()
        self._on_event = on_event

    def emit(self, event: Event) -> None:
        self.events.append((round((time.monotonic() - self._start) * 1000), event))
        self._on_event(event)


class _BrokenExecutor:
    """Fails like a lost container on one stage."""

    def __init__(self, inner: Executor, stage: str) -> None:
        self._inner, self._stage = inner, stage

    def __enter__(self) -> Self:
        self._inner.__enter__()
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._inner.__exit__(kind, error, tb)

    def run(
        self,
        stage_key: str,
        plan: StagePlan,
        on_line: OnLine,
        cancel: threading.Event,
        *,
        reuse_dir: bool = False,
    ) -> ExecResult:
        if stage_key == self._stage:
            raise ExecutorError("the sandbox container is gone")
        return self._inner.run(stage_key, plan, on_line, cancel, reuse_dir=reuse_dir)


@dataclass(frozen=True)
class Recording:
    results: list[StageResult]
    events: list[tuple[int, Event]]
    artifacts: dict[tuple[str, str], bytes]


def record(scenario: Scenario, code: str, image: str) -> Recording:
    package = PROBLEMS / scenario.problem
    problem = load_manifest(package)
    classes = load_resource_classes(RESOURCE_CLASSES)
    if scenario.output_kb is not None:
        resource = classes.classes[problem.resource_class]
        limited = resource.model_copy(update={"output_kb": scenario.output_kb})
        classes = ResourceClasses(classes={**classes.classes, problem.resource_class: limited})
    cancel = threading.Event()

    def on_event(event: Event) -> None:
        if scenario.cancel and isinstance(event, StageStartEvent):
            stage, delay = scenario.cancel
            if event.stage == stage:
                threading.Timer(delay, cancel.set).start()

    sink = _Recorder(on_event)
    artifacts: dict[tuple[str, str], bytes] = {}
    executor: Executor = LocalDockerExecutor(image, sandbox_limits(problem, classes))
    if scenario.broken_stage:
        executor = _BrokenExecutor(executor, scenario.broken_stage)
    job = Job(problem, package, scenario.kind, SEED, code.encode())
    with executor:
        results = run_pipeline(
            job,
            get_language(problem.language),
            executor,
            sink,
            classes,
            cancel,
            on_artifact=lambda stage, name, data: artifacts.__setitem__((stage, name), data),
        )
    return Recording(results, sink.events, artifacts)


def first_attempt(events: Sequence[tuple[int, Event]], stage: str) -> list[tuple[int, Event]]:
    """The events of an attempt whose worker died after the stage: up to the next stage start."""
    end = next(
        i
        for i, (_, e) in enumerate(events)
        if isinstance(e, StageEndEvent) and e.result.key == stage
    )
    return list(events[: end + 2])


def scenario_document(name: str, scenario: Scenario, image: str) -> dict[str, Any]:
    package = PROBLEMS / scenario.problem
    problem = load_manifest(package)
    code = scenario.solution(package)
    created = datetime.now(UTC).replace(microsecond=0)
    print(f"# {name}: {scenario.problem} {scenario.kind}", flush=True)
    recording = record(scenario, code, image)
    verdict = aggregate(recording.results)

    attempts = []
    offset = STARTED_MS
    if scenario.retry_after:
        died = first_attempt(recording.events, scenario.retry_after)
        attempts.append(worker_events([(offset + ms, e) for ms, e in died], attempt=1))
        offset = attempts[-1][-1][0] + 3000  # the lease expires, the check is queued again
    attempts.append(
        worker_events([(offset + ms, e) for ms, e in recording.events], len(attempts) + 1)
    )
    events = timeline(attempts, verdict)
    created_ms = round(created.timestamp() * 1000)
    numbered = stream_ids(created_ms, events)

    logs = {
        result.key: "".join(
            data["text"]
            for _, data in attempts[-1]
            if data.get("stage") == result.key and data["type"] == "log"
        )
        for result in recording.results
        if result.started_at is not None
    }
    traces = {
        stage: data for (stage, file), data in recording.artifacts.items() if file.endswith(".fst")
    }
    artifacts = [artifact("log", stage, len(text.encode())) for stage, text in logs.items()]
    for stage, data in traces.items():
        artifacts.append(artifact("fst", stage, len(data), trace_window(recording.results, stage)))
    events_bytes = b"".join(json.dumps(e, ensure_ascii=False).encode() + b"\n" for e in numbered)
    artifacts.append(artifact("events", None, len(events_bytes)))

    started = min(r.started_at for r in recording.results if r.started_at is not None)
    submission = {
        "id": str(uuid7(created_ms)),
        "problem": problem.id,
        "problem_title": problem.title,
        "version": problem.version,
        "kind": scenario.kind,
        "status": verdict.status,
        "verdict_detail": verdict.detail.model_dump(mode="json"),
        "created_at": created.isoformat(),
        "finished_at": (created + timedelta(milliseconds=events[-1][0])).isoformat(),
        "code": code,
        "public": False,
        "leaderboard": None,
        "seed": str(SEED),
        "toolchain_profile": PROFILE,
        "waveview_url": None,  # recordings name no viewer
        "queue_position": None,
        "eta_s": None,
        "started_at": started.isoformat(),
        "stages": [stage_document(r) for r in recording.results],
        "artifacts": artifacts,
    }
    document: dict[str, Any] = {"name": name, "submission": submission, "events": numbered}
    if traces:
        [trace] = traces.values()
        document["files"] = {"fst": base64.b64encode(trace).decode()}
    print(f"  {verdict.status}, {len(numbered)} events, {events[-1][0] / 1000:.1f} s", flush=True)
    return document


def stage_document(result: StageResult) -> dict[str, Any]:
    """A stage of `GET /submissions/{id}`."""
    data = result.model_dump(mode="json", exclude={"limit", "cached"})
    finished = (
        result.started_at + timedelta(milliseconds=result.duration_ms)
        if result.started_at is not None and result.duration_ms is not None
        else None
    )
    data["finished_at"] = finished.isoformat() if finished else None
    return data


def artifact(
    kind: str, stage: str | None, size: int, waveform: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "kind": kind,
        "stage": stage,
        "state": "ready",
        "size_bytes": size,
        "error_code": None,
        "waveform": waveform,
    }


def trace_window(results: Sequence[StageResult], stage: str) -> dict[str, Any]:
    metrics = next(r.metrics for r in results if r.key == stage)
    begin, end = metrics["trace_window"]
    failure = metrics["first_failure"]
    return {
        "test": failure["test"],
        "scope": "failure_window",
        "from_cycle": begin,
        "to_cycle": end,
        "cursor_cycle": failure["cycle"],
        "cursor_time_ps": metrics["trace_cursor_ps"],
        "signals": metrics["trace_signals"],
    }


def uuid7(ms: int) -> uuid.UUID:
    value = (
        (ms << 80)
        | (0x7 << 76)
        | (secrets.randbits(12) << 64)
        | (0b10 << 62)
        | secrets.randbits(62)
    )
    return uuid.UUID(int=value)


# --- stand-ins at parameter sets ---------------------------------------------------------------

# The judge does not expand stages by parameter sets yet (ADR-0014). Until it does, these checks of
# sync-fifo at its primary set and a narrow one are put together from the recordings `accepted`
# and `wrong-answer`: an instance at the narrow set repeats the logs, the metrics and the trace of
# the primary set.
PRIMARY = ParamSet(id="default", values={"WIDTH": 8, "DEPTH": 16})
NARROW = ParamSet(id="narrow", values={"WIDTH": 1, "DEPTH": 2})
EXPANDED = ("sim_full", "synth", "netlist_sim")  # the stages with `param_sets: all`
STAND_INS = ("accepted-param-sets", "wrong-answer-param-set")
STAGE_GAP_MS = 40  # from the end of an instance to the start of the next one


def stage_events(document: dict[str, Any]) -> dict[str, list[Timed]]:
    """The events of each stage of a recording, in ms since the submission was created."""
    created = round(datetime.fromisoformat(document["submission"]["created_at"]).timestamp() * 1000)
    stages: dict[str, list[Timed]] = {}
    for item in document["events"]:
        data = item["event"]
        key = data.get("stage") or data.get("result", {}).get("key")
        if key is not None:
            stages.setdefault(key, []).append((int(item["id"].split("-")[0]) - created, data))
    return stages


def instance(
    events: Sequence[Timed],
    key: str,
    ordinal: int,
    param_set: ParamSet | None,
    at: int,
    moved: timedelta,
    update: dict[str, Any],
) -> tuple[list[Timed], StageResult]:
    """The events and the result of a recorded stage as an instance that starts at `at` ms;
    `moved`: from the creation of the recorded submission to the creation of the new one."""
    begin = events[0][0]
    shift = moved + timedelta(milliseconds=at - begin)
    placed: list[Timed] = []
    result: StageResult | None = None
    for ms, recorded in events:
        data = {**recorded, "stage": key} if "stage" in recorded else dict(recorded)
        if data["type"] == "stage_start":
            data |= {"ordinal": ordinal, "param_set": param_set and param_set.model_dump()}
        if data["type"] == "stage_end":
            stage = StageResult.model_validate(data["result"])
            result = stage.model_copy(
                update={
                    "key": key,
                    "ordinal": ordinal,
                    "param_set": param_set,
                    "started_at": stage.started_at and stage.started_at + shift,
                }
                | update
            )
            data["result"] = result.model_dump(mode="json")
        placed.append((at + ms - begin, data))
    assert result is not None, f"no result of {key}"
    return placed, result


def stand_in(
    name: str, accepted: dict[str, Any], wrong: dict[str, Any] | None = None
) -> dict[str, Any]:
    """`accepted` at both sets; with `wrong`, its failed open test fails `sim_full` at the narrow
    set and the instances after it are skipped."""
    recorded = stage_events(accepted)
    created = datetime.fromisoformat(accepted["submission"]["created_at"])
    plan = [
        (stage, param_set)
        for stage in recorded
        for param_set in ((PRIMARY, NARROW) if stage in EXPANDED else (None,))
    ]
    worker: list[Timed] = []
    results: list[StageResult] = []
    artifacts: list[dict[str, Any]] = []
    at = recorded["precheck"][0][0]
    for ordinal, (stage, param_set) in enumerate(plan):
        key = stage if param_set in (None, PRIMARY) else f"{stage}@{NARROW.id}"
        if any(r.status == "failed" for r in results):
            skipped = StageResult(
                key=key,
                type=recorded[stage][-1][1]["result"]["type"],
                ordinal=ordinal,
                param_set=param_set,
                status="skipped",
                summary=StageSummary(skip_reason="previous_failed"),
            )
            results.append(skipped)
            end = {"type": "stage_end", "result": skipped.model_dump(mode="json"), "attempt": 1}
            worker.append((at, end))
            continue
        source, source_stage, update = accepted, stage, {}
        if wrong is not None and key == f"sim_full@{NARROW.id}":
            # The open test fails at the narrow set; the hidden tests do not run.
            source, source_stage = wrong, "sim_run"
            failed = StageResult.model_validate(stage_events(wrong)["sim_run"][-1][1]["result"])
            update = {
                "metrics": failed.metrics | {"tests_total": results[-1].metrics["tests_total"]},
                "summary": failed.summary.model_copy(
                    update={"hidden_tests": HiddenTests(total=2, passed=0)}
                ),
            }
        moved = created - datetime.fromisoformat(source["submission"]["created_at"])
        events, result = instance(
            stage_events(source)[source_stage], key, ordinal, param_set, at, moved, update
        )
        worker += events
        results.append(result)
        artifacts += [
            a | {"stage": key}
            for a in source["submission"]["artifacts"]
            if a["stage"] == source_stage
        ]
        at = events[-1][0] + (0 if result.status == "failed" else STAGE_GAP_MS)
    worker.append((at, {"type": "done", "attempt": 1}))

    verdict = aggregate(results)
    events = timeline([worker], verdict)
    submission = accepted["submission"]
    numbered = stream_ids(round(created.timestamp() * 1000), events)
    events_bytes = b"".join(json.dumps(e, ensure_ascii=False).encode() + b"\n" for e in numbered)
    artifacts.append(artifact("events", None, len(events_bytes)))
    # The id of the recording with its random bits replaced: stable from run to run.
    salt = int(hashlib.sha256(name.encode()).hexdigest()[:12], 16)
    document: dict[str, Any] = {
        "name": name,
        "submission": submission
        | {
            "id": str(uuid.UUID(int=uuid.UUID(submission["id"]).int >> 48 << 48 | salt)),
            "status": verdict.status,
            "verdict_detail": verdict.detail.model_dump(mode="json"),
            "finished_at": (created + timedelta(milliseconds=events[-1][0])).isoformat(),
            "stages": [stage_document(r) for r in results],
            "artifacts": artifacts,
        },
        "events": numbered,
    }
    if wrong is not None:
        document["files"] = wrong["files"]
    return document


def stand_ins() -> dict[str, str]:
    """The files of the stand-ins, from the recordings in OUTPUT."""
    accepted, wrong = (
        json.loads((OUTPUT / f"{name}.json").read_text(encoding="utf-8"))
        for name in ("accepted", "wrong-answer")
    )
    return {
        "accepted-param-sets": dump(stand_in("accepted-param-sets", accepted)),
        "wrong-answer-param-set": dump(stand_in("wrong-answer-param-set", accepted, wrong)),
    }


def dump(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, indent=1) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "names", nargs="*", metavar="name", help=", ".join([*SCENARIOS, *STAND_INS])
    )
    parser.add_argument("--image", default=os.environ.get("JUDGE_TOOLCHAIN_IMAGE", DEFAULT_IMAGE))
    args = parser.parse_args(argv)
    unknown = set(args.names) - set(SCENARIOS) - set(STAND_INS)
    if unknown:
        parser.error(f"unknown scenarios: {', '.join(sorted(unknown))}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name in [n for n in args.names if n in SCENARIOS] if args.names else SCENARIOS:
        document = scenario_document(name, SCENARIOS[name], args.image)
        (OUTPUT / f"{name}.json").write_text(dump(document), encoding="utf-8", newline="\n")
    for name, text in stand_ins().items():
        (OUTPUT / f"{name}.json").write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
