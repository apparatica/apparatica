"""What a worker reports of an attempt and how it records its console (specs/07 §4).

The ingestor turns a report into stage rows, artifacts and the verdict (ADR-0009). Until the results
stream arrives (T1.3) the report is only logged.
"""

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol

import structlog

from apparatica_worker.storage import StoredArtifact
from judge.core.events import EVENT, Event, EventSink, LogEvent
from judge.core.jobs import JudgeJob
from judge.core.stage import StageResult

log = structlog.get_logger(__name__)

# Why an attempt ended without running the pipeline; the ingestor reports internal_error.
ATTEMPTS_EXHAUSTED = "ATTEMPTS_EXHAUSTED"
PACKAGE_UNAVAILABLE = "PACKAGE_UNAVAILABLE"
SANDBOX_UNAVAILABLE = "SANDBOX_UNAVAILABLE"


@dataclass(frozen=True)
class AttemptReport:
    job: JudgeJob
    attempt: int
    results: tuple[StageResult, ...] = ()
    artifacts: tuple[StoredArtifact, ...] = ()
    error_code: str | None = None  # the pipeline did not run


class Reporter(Protocol):
    def report(self, report: AttemptReport) -> None: ...


class LogReporter:
    """Until T1.3: the report goes to the log only."""

    def report(self, report: AttemptReport) -> None:
        log.info(
            "attempt finished",
            submission_id=str(report.job.submission_id),
            attempt=report.attempt,
            error_code=report.error_code,
            stages={result.key: result.status for result in report.results},
            artifacts=[artifact.key for artifact in report.artifacts],
        )


class NullSink:
    def emit(self, event: Event) -> None:
        pass


class RecordingSink:
    """Keeps the console of each stage and every event of the attempt for the artifacts
    (`logs/<stage>.log`, `events.jsonl`), and passes the events on."""

    def __init__(self, attempt: int, inner: EventSink) -> None:
        self._attempt = attempt
        self._inner = inner
        self.logs: dict[str, list[str]] = defaultdict(list)
        self.events: list[bytes] = []

    def emit(self, event: Event) -> None:
        if isinstance(event, LogEvent):
            self.logs[event.stage].append(event.text)
        record = json.loads(EVENT.dump_json(event)) | {"attempt": self._attempt}
        self.events.append(json.dumps(record, ensure_ascii=False).encode() + b"\n")
        self._inner.emit(event)

    def log_text(self, stage: str) -> bytes:
        return "".join(line + "\n" for line in self.logs.get(stage, ())).encode()
