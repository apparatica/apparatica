"""Testbench result protocol of `apx_tb_pkg` (specs/06 §3.3).

Two channels: the result file (JSON Lines, authoritative) and progress lines `@@apx:<nonce> <json>`
in the simulation stdout (live progress only). Both come from the sandbox and are untrusted: the
file is size-checked before parsing, every record is validated against the models below, and the
record order is checked. The models are the source of truth for the record format; the JSON Schema
is generated from them (`judge schema tb-result` → judge/schemas/tb-result.schema.json).
"""

import json
import secrets
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    field_validator,
)
from pydantic_core import ErrorDetails

SCHEMA_ID = "https://apparatica.app/schemas/tb-result/1.json"
PROGRESS_PREFIX = "@@apx:"
HINT_MAX_LENGTH = 500

Name = Annotated[str, StringConstraints(min_length=1)]
# Width and hex digits, as apx_tb_pkg prints them: 8'h3a.
Value = Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]*'h[0-9a-f]+$")]


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    v: Literal[1]


class SuiteStart(_Record):
    event: Literal["suite_start"]
    seed: int = Field(ge=0, lt=2**64)
    groups: list[Name] | None = Field(description="Selected groups; null: all groups")


class TestStart(_Record):
    event: Literal["test_start"]
    id: Name
    name: str
    group: Name
    cycle: NonNegativeInt


class Mismatch(_Record):
    event: Literal["mismatch"]
    test: Name
    cycle: NonNegativeInt
    time_ps: NonNegativeInt
    signal: Name
    expected: Value
    actual: Value
    hint: str | None = Field(default=None, description=f"Shown up to {HINT_MAX_LENGTH} characters")

    @field_validator("hint")
    @classmethod
    def _truncate_hint(cls, hint: str | None) -> str | None:
        # A long hint is the author's mistake, not a broken result: cut it instead of rejecting.
        if hint is not None and len(hint) > HINT_MAX_LENGTH:
            return hint[: HINT_MAX_LENGTH - 1] + "…"
        return hint


class TestEnd(_Record):
    event: Literal["test_end"]
    id: Name
    status: Literal["passed", "failed"]
    cycles: NonNegativeInt
    cycle: NonNegativeInt


class TestSkip(_Record):
    """A test not run because an earlier test failed."""

    event: Literal["test_skip"]
    id: Name
    name: str
    group: Name


class SuiteEnd(_Record):
    event: Literal["suite_end"]
    passed: NonNegativeInt
    failed: NonNegativeInt
    not_run: NonNegativeInt
    cycles: NonNegativeInt


class SuiteAbort(_Record):
    """The run stopped early: the cycle limit (`max_cycles`) or a testbench bug (`tb_error`)."""

    event: Literal["suite_abort"]
    reason: Literal["max_cycles", "tb_error"]
    cycle: NonNegativeInt
    message: str | None = None


type Record = Annotated[
    SuiteStart | TestStart | Mismatch | TestEnd | TestSkip | SuiteEnd | SuiteAbort,
    Field(discriminator="event"),
]
# Progress lines carry every record except mismatches: values of hidden tests never reach stdout.
type ProgressRecord = Annotated[
    SuiteStart | TestStart | TestEnd | TestSkip | SuiteEnd | SuiteAbort,
    Field(discriminator="event"),
]

_RECORD: TypeAdapter[Record] = TypeAdapter(Record)
_PROGRESS: TypeAdapter[ProgressRecord] = TypeAdapter(ProgressRecord)


class ProtocolError(Exception):
    """The result file breaks the protocol: the stage fails with OUTPUT_INVALID (specs/07 §5.2)."""

    def __init__(self, message: str, line: int | None = None) -> None:
        super().__init__(message if line is None else f"line {line}: {message}")
        self.line = line


@dataclass(frozen=True)
class TestCase:
    id: str
    name: str
    group: str
    status: Literal["passed", "failed", "not_run", "running"]
    start_cycle: int | None = None
    end_cycle: int | None = None
    mismatches: tuple[Mismatch, ...] = ()


@dataclass(frozen=True)
class TbResult:
    """The parsed result file. `end` is None if the run did not finish the suite: the simulation
    crashed, timed out or was killed, or `abort` says why it stopped."""

    start: SuiteStart | None
    tests: tuple[TestCase, ...]
    end: SuiteEnd | None
    abort: SuiteAbort | None
    truncated: bool  # the last line was cut off mid-record and ignored

    @property
    def first_mismatch(self) -> Mismatch | None:
        return next((m for test in self.tests for m in test.mismatches), None)


def parse_result(data: bytes, *, max_bytes: int) -> TbResult:
    """Parse the result file written by apx_tb_pkg.

    Raises ProtocolError if the file is larger than `max_bytes`, a complete line is not a valid
    record, or the records break the protocol order. A missing tail is not an error: the result
    then has no `end`, and the stage decides the verdict (specs/06 §3.3).
    """
    if len(data) > max_bytes:
        raise ProtocolError(f"the result file exceeds {max_bytes} bytes")
    *lines, tail = data.split(b"\n")
    builder = _Builder()
    for number, line in enumerate(lines, start=1):
        builder.add(_parse_line(line, number), number)
    if tail and builder.closed:
        raise ProtocolError("data after the end of the suite", len(lines) + 1)
    return builder.result(truncated=bool(tail))


def _parse_line(line: bytes, number: int) -> Record:
    try:
        return _RECORD.validate_json(line)
    except ValidationError as error:
        problems = "; ".join(_describe(e) for e in error.errors(include_url=False))
        raise ProtocolError(problems, number) from None


def _describe(error: ErrorDetails) -> str:
    location = ".".join(str(part) for part in error["loc"])
    return f"{location}: {error['msg']}" if location else error["msg"]


class _Builder:
    """Checks the record order of one run and collects the tests."""

    def __init__(self) -> None:
        self.start: SuiteStart | None = None
        self.tests: list[TestCase] = []
        self.ids: set[str] = set()
        self.current: TestStart | None = None
        self.mismatches: list[Mismatch] = []
        self.failed = False
        self.end: SuiteEnd | None = None
        self.abort: SuiteAbort | None = None

    @property
    def closed(self) -> bool:
        return self.end is not None or self.abort is not None

    def add(self, record: Record, line: int) -> None:
        if self.closed:
            raise ProtocolError(f"{record.event} after the end of the suite", line)
        if self.start is None and not isinstance(record, SuiteStart):
            raise ProtocolError(f"{record.event} before suite_start", line)
        match record:
            case SuiteStart():
                if self.start is not None:
                    raise ProtocolError("second suite_start", line)
                self.start = record
            case TestStart() | TestSkip():
                self._new_test(record, line)
            case Mismatch():
                if self.current is None or record.test != self.current.id:
                    raise ProtocolError(f"mismatch of {record.test} outside that test", line)
                if record.cycle < self.current.cycle:
                    raise ProtocolError("mismatch before the start of its test", line)
                self.mismatches.append(record)
            case TestEnd():
                self._end_test(record, line)
            case SuiteEnd():
                if self.current is not None:
                    raise ProtocolError(f"suite_end inside test {self.current.id}", line)
                counted = (
                    sum(t.status == "passed" for t in self.tests),
                    sum(t.status == "failed" for t in self.tests),
                    sum(t.status == "not_run" for t in self.tests),
                )
                if (record.passed, record.failed, record.not_run) != counted:
                    raise ProtocolError("suite_end counts do not match the tests", line)
                self.end = record
            case SuiteAbort():
                self.abort = record

    def _new_test(self, record: TestStart | TestSkip, line: int) -> None:
        if self.current is not None:
            raise ProtocolError(f"{record.event} {record.id} inside test {self.current.id}", line)
        if record.id in self.ids:
            raise ProtocolError(f"duplicate test id {record.id}", line)
        assert self.start is not None
        if self.start.groups is not None and record.group not in self.start.groups:
            raise ProtocolError(f"test {record.id} of a group that was not selected", line)
        # After a failed test the suite only skips the rest (specs/06 §3.1).
        if isinstance(record, TestSkip) != self.failed:
            raise ProtocolError(f"{record.event} {record.id} contradicts the failed tests", line)
        self.ids.add(record.id)
        if isinstance(record, TestSkip):
            self.tests.append(TestCase(record.id, record.name, record.group, "not_run"))
        else:
            self.current = record
            self.mismatches = []

    def _end_test(self, record: TestEnd, line: int) -> None:
        current = self.current
        if current is None or record.id != current.id:
            raise ProtocolError(f"test_end of {record.id} outside that test", line)
        if record.cycle < current.cycle or record.cycles != record.cycle - current.cycle:
            raise ProtocolError(f"test_end cycles of {record.id} do not match its start", line)
        if (record.status == "failed") != bool(self.mismatches):
            raise ProtocolError(f"test {record.id} status does not match its mismatches", line)
        self.tests.append(self._case(current, record.status, record.cycle))
        self.failed = self.failed or record.status == "failed"
        self.current = None

    def _case(
        self, start: TestStart, status: Literal["passed", "failed", "running"], end: int | None
    ) -> TestCase:
        return TestCase(
            start.id, start.name, start.group, status, start.cycle, end, tuple(self.mismatches)
        )

    def result(self, *, truncated: bool) -> TbResult:
        tests = list(self.tests)
        if self.current is not None:
            tests.append(self._case(self.current, "running", None))
        return TbResult(self.start, tuple(tests), self.end, self.abort, truncated)


def new_nonce() -> str:
    """A per-run secret for progress lines (+apx_nonce); the solution cannot read plusargs."""
    return secrets.token_hex(16)


def split_progress(line: str, nonce: str) -> tuple[str, ProgressRecord | None]:
    """Split a stdout line into console text and a progress record.

    The marker is searched anywhere in the line: the solution may `$write` text without a newline
    right before the record. A line without the run's nonce is plain console text; a record with
    the right nonce but an invalid payload is dropped from both.
    """
    marker = f"{PROGRESS_PREFIX}{nonce} "
    position = line.find(marker) if nonce else -1
    if position < 0:
        return line, None
    text, payload = line[:position], line[position + len(marker) :]
    try:
        return text, _PROGRESS.validate_json(payload.rstrip("\r\n"))
    except ValidationError:
        return text, None


def tb_result_json_schema() -> str:
    """JSON Schema of one result file record, generated from the models (draft 2020-12)."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "Apparatica testbench result record (one JSON Lines record of apx_tb_pkg)",
    }
    schema |= _RECORD.json_schema(mode="validation")
    return json.dumps(schema, ensure_ascii=False, indent=2) + "\n"
