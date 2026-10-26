"""What a worker reports of an attempt and how it records its console (specs/07 §4).

The ingestor turns a report into stage rows, artifacts and the verdict (ADR-0009): the report goes
to `judge:results` as `done` or, when the pipeline did not run, `attempt_failed`.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol

import structlog

from apparatica_worker.stream import ResultsStream
from judge.core.events import Event, LogEvent
from judge.core.jobs import AttemptFailedRecord, DoneRecord, JudgeJob, StoredArtifact
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
    cancelled: bool = False  # by the user or by a newer run


class Reporter(Protocol):
    def report(self, report: AttemptReport) -> None: ...


class StreamReporter:
    """The report to the ingestor through `judge:results`, and to the log."""

    def __init__(self, results: ResultsStream) -> None:
        self._results = results

    def report(self, report: AttemptReport) -> None:
        log.info(
            "attempt finished",
            submission_id=str(report.job.submission_id),
            attempt=report.attempt,
            error_code=report.error_code,
            cancelled=report.cancelled,
            stages={result.key: result.status for result in report.results},
            artifacts=[artifact.key for artifact in report.artifacts],
        )
        job, attempt = report.job, report.attempt
        record: AttemptFailedRecord | DoneRecord
        if report.error_code is not None:
            record = AttemptFailedRecord(
                submission_id=job.submission_id,
                attempt=attempt,
                token=job.token,
                error_code=report.error_code,
            )
        else:
            record = DoneRecord(
                submission_id=job.submission_id,
                attempt=attempt,
                token=job.token,
                results=report.results,
                artifacts=report.artifacts,
                cancelled=report.cancelled,
            )
        self._results.write(record, final=True)


class RecordingSink:
    """Keeps the console of each stage for the artifacts (`logs/<stage>.log`)."""

    def __init__(self) -> None:
        self.logs: dict[str, list[str]] = defaultdict(list)

    def emit(self, event: Event) -> None:
        if isinstance(event, LogEvent):
            self.logs[event.stage].append(event.text)

    def log_text(self, stage: str) -> bytes:
        return "".join(line + "\n" for line in self.logs.get(stage, ())).encode()
