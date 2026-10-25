"""Pipeline events and their sinks (specs/07 §4.1).

The events are the worker's stream events without `attempt` (the worker adds it): the console of
`judge run`, a JSONL file and the Valkey stream of the worker are sinks of the same events.
"""

import sys
from typing import Annotated, BinaryIO, Literal, Protocol, TextIO

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from judge.core.stage import Channel, StageResult, TestCase


class _Event(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StageStartEvent(_Event):
    type: Literal["stage_start"] = "stage_start"
    stage: str
    stage_type: str
    ordinal: int


class LogEvent(_Event):
    type: Literal["log"] = "log"
    stage: str
    ch: Channel
    text: str


class TestEvent(_Event):
    type: Literal["test"] = "test"
    stage: str
    test: TestCase


class TruncatedEvent(_Event):
    type: Literal["truncated"] = "truncated"
    stage: str
    limit_kb: int


class StageEndEvent(_Event):
    type: Literal["stage_end"] = "stage_end"
    result: StageResult


class DoneEvent(_Event):
    type: Literal["done"] = "done"


type Event = Annotated[
    StageStartEvent | LogEvent | TestEvent | TruncatedEvent | StageEndEvent | DoneEvent,
    Field(discriminator="type"),
]
EVENT: TypeAdapter[Event] = TypeAdapter(Event)


class EventSink(Protocol):
    def emit(self, event: Event) -> None: ...


class JsonlSink:
    """One JSON event per line, e.g. `events.jsonl` of `judge run`."""

    def __init__(self, stream: BinaryIO) -> None:
        self._stream = stream

    def emit(self, event: Event) -> None:
        self._stream.write(EVENT.dump_json(event) + b"\n")
        self._stream.flush()


class ConsoleSink:
    """Human-readable console: stage separators, log lines, test progress, stage results."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream or sys.stdout

    def emit(self, event: Event) -> None:
        match event:
            case StageStartEvent():
                self._write(f"── {event.stage} ".ljust(60, "─"))
            case LogEvent(ch="err"):
                self._write(f"! {event.text}")
            case LogEvent(ch="sys"):
                self._write(f"# {event.text}")
            case LogEvent():
                self._write(event.text)
            case TestEvent():
                self._write(f"test {event.test.id} ({event.test.name}): {event.test.status}")
            case TruncatedEvent():
                self._write(f"# output truncated at {event.limit_kb} KB")
            case StageEndEvent():
                self._write(_describe(event.result))
            case DoneEvent():
                pass

    def _write(self, line: str) -> None:
        self._stream.write(line + "\n")
        self._stream.flush()


def _describe(result: StageResult) -> str:
    details = [
        detail
        for detail in (result.failure_kind, result.limit, result.error_code, result.summary.caption)
        if detail
    ]
    if result.summary.skip_reason:
        details.append(result.summary.skip_reason)
    if result.duration_ms is not None:
        details.append(f"{result.duration_ms / 1000:.1f} s")
    suffix = f" ({', '.join(details)})" if details else ""
    return f"{result.key}: {result.status}{suffix}"


class FanoutSink:
    def __init__(self, *sinks: EventSink) -> None:
        self._sinks = sinks

    def emit(self, event: Event) -> None:
        for sink in self._sinks:
            sink.emit(event)
