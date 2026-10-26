"""Applying the records of `judge:results` to the database (ADR-0009, specs/07 §1).

Each record is checked against the job token of its submission and applied in one transaction
under a row lock of the submission, so that a redelivered or reordered record changes nothing:

- records of an attempt older than the submission's are void: a worker that lost its lease may
  still report; `attempt_started` (or any record) of a newer attempt voids the stage results of
  the older one;
- stage results are upserted by (submission, stage key);
- `done` stores every stage result of the attempt and its artifacts and aggregates the verdict
  with the judge core; `attempt_failed` ends the check with internal_error;
- a finished submission takes no more records; a final record for it publishes `finalized` again,
  in case the first publication was lost.
"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, get_args

import structlog
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DataError, DBAPIError, IntegrityError, InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.core.db import Database
from apparatica.core.ids import uuid7
from apparatica.judging.retention import Retention
from apparatica.submissions.events import FinalizedEvent
from apparatica.submissions.models import Artifact, Submission
from apparatica.submissions.models import StageResult as StageResultRow
from apparatica.submissions.tokens import InvalidJobTokenError, JobTokens
from judge.core.jobs import (
    AttemptFailedRecord,
    AttemptStartedRecord,
    DoneRecord,
    ResultRecord,
    StageEndRecord,
    StoredArtifact,
)
from judge.core.stage import StageResult, SubmissionKind
from judge.core.verdict import SubmissionStatus, Verdict, VerdictDetail, aggregate

log = structlog.get_logger(__name__)

FINAL_STATUSES = frozenset(get_args(SubmissionStatus))
EMPTY_PIPELINE = "EMPTY_PIPELINE"  # a `done` without stage results: nothing was checked
# Columns of a stage result that a later record of the same attempt replaces.
_STAGE_COLUMNS = (
    "stage_type",
    "ordinal",
    "status",
    "failure_kind",
    "started_at",
    "finished_at",
    "duration_ms",
    "metrics",
    "metrics_schema",
    "summary",
    "error_code",
)


def transient(error: BaseException) -> bool:
    """The database or Valkey is unreachable: try again later, drop nothing."""
    if isinstance(error, DBAPIError):
        return isinstance(error, OperationalError | InterfaceError) or error.connection_invalidated
    return isinstance(error, OSError | RedisConnectionError | RedisTimeoutError)


class InvalidRecordError(Exception):
    """The record cannot be applied and never will be: it is dropped."""


@dataclass(frozen=True)
class Ingestor:
    database: Database
    tokens: JobTokens
    retention: Retention
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))

    async def ingest(self, record: ResultRecord) -> FinalizedEvent | None:
        """Apply one record; the `finalized` event to publish when it ended the check.

        Raises InvalidRecordError for a record to drop; database errors of the connection
        propagate, and the record is retried."""
        try:
            self.tokens.verify(record.token, record.submission_id)
        except InvalidJobTokenError as error:
            raise InvalidRecordError(f"job token: {error}") from error
        try:
            async with self.database.sessions.begin() as session:
                return await self._apply(session, record)
        except (IntegrityError, DataError) as error:  # e.g. a stage result the schema refuses
            raise InvalidRecordError(f"refused by the database: {error.orig}") from error

    async def cancel_waiting(self, submission_id: uuid.UUID) -> FinalizedEvent | None:
        """A cancelled check that no worker has started ends now (specs/07 §3); a running one
        ends when its worker reports it."""
        async with self.database.sessions.begin() as session:
            submission = await session.get(Submission, submission_id, with_for_update=True)
            if submission is None or submission.status != "queued":
                return None
            log.info("waiting check cancelled", submission_id=str(submission_id))
            return finalize(submission, Verdict(status="cancelled"), self.clock())

    async def _apply(self, session: AsyncSession, record: ResultRecord) -> FinalizedEvent | None:
        submission = await session.get(Submission, record.submission_id, with_for_update=True)
        if submission is None:  # deleted meanwhile, e.g. an old guest submission
            raise InvalidRecordError("no such submission")
        final = isinstance(record, DoneRecord | AttemptFailedRecord)
        if submission.status in FINAL_STATUSES:
            return finalized(submission) if final else None
        if record.attempt < submission.attempt:
            log.info(
                "record of an earlier attempt dropped",
                submission_id=str(submission.id),
                attempt=record.attempt,
                current=submission.attempt,
            )
            return None
        now = self.clock()
        # The attempt after the last one only reports that there are no attempts left.
        if record.attempt > submission.attempt and not isinstance(record, AttemptFailedRecord):
            await session.execute(
                delete(StageResultRow).where(StageResultRow.submission_id == submission.id)
            )
            submission.attempt = record.attempt
        if submission.status == "queued":
            submission.status = "running"
        if submission.started_at is None:
            submission.started_at = now

        match record:
            case AttemptStartedRecord():
                return None
            case StageEndRecord():
                await _upsert_stages(session, submission.id, [record.result])
                return None
            case DoneRecord():
                await _upsert_stages(session, submission.id, record.results)
                await self._store_artifacts(session, submission, record)
                if record.results or record.cancelled:  # cancelled while waiting: nothing ran
                    verdict = aggregate(record.results, cancelled=record.cancelled)
                else:
                    verdict = internal_error(EMPTY_PIPELINE)
            case AttemptFailedRecord():
                verdict = internal_error(record.error_code)
        log.info(
            "check finalized",
            submission_id=str(submission.id),
            attempt=record.attempt,
            status=verdict.status,
        )
        return finalize(submission, verdict, now)

    async def _store_artifacts(
        self, session: AsyncSession, submission: Submission, record: DoneRecord
    ) -> None:
        stored = self.clock()
        rows: list[dict[str, Any]] = [
            {
                "id": uuid7(),
                "submission_id": submission.id,
                "stage_key": artifact.stage,
                "kind": artifact.kind,
                "storage_key": artifact.key,
                "size_bytes": artifact.size_bytes,
                "sha256": artifact.sha256,
                "expires_at": self.retention.expires_at(_kind(submission), artifact.kind, stored),
            }
            for artifact in record.artifacts
            if _owned(artifact, record)
        ]
        if rows:
            await session.execute(
                insert(Artifact).values(rows).on_conflict_do_nothing(index_elements=["storage_key"])
            )


async def _upsert_stages(
    session: AsyncSession, submission_id: uuid.UUID, results: Sequence[StageResult]
) -> None:
    if not results:
        return
    rows = [
        {
            "id": uuid7(),
            "submission_id": submission_id,
            "stage_key": result.key,
            "stage_type": result.type,
            "ordinal": result.ordinal,
            "status": result.status,
            "failure_kind": result.failure_kind,
            "started_at": result.started_at,
            "finished_at": (
                result.started_at + timedelta(milliseconds=result.duration_ms)
                if result.started_at is not None and result.duration_ms is not None
                else None
            ),
            "duration_ms": result.duration_ms,
            "metrics": result.metrics,
            "metrics_schema": result.metrics_schema,
            "summary": result.summary.model_dump(mode="json"),
            "error_code": result.error_code,
        }
        for result in results
    ]
    statement = insert(StageResultRow).values(rows)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["submission_id", "stage_key"],
            set_={column: statement.excluded[column] for column in _STAGE_COLUMNS},
        )
    )


def _owned(artifact: StoredArtifact, record: DoneRecord) -> bool:
    """An artifact of this attempt of this submission (`<yyyy>/<mm>/<id>/<attempt>/…`): a worker
    must not attach the files of another check."""
    parts = artifact.key.split("/")
    if parts[2:4] == [str(record.submission_id), str(record.attempt)] and len(parts) > 4:
        return True
    log.warning(
        "foreign artifact dropped", submission_id=str(record.submission_id), key=artifact.key
    )
    return False


def _kind(submission: Submission) -> SubmissionKind:
    return "submit" if submission.kind == "submit" else "run"


def internal_error(code: str) -> Verdict:
    return Verdict(status="internal_error", detail=VerdictDetail(error_codes=[code]))


def finalize(submission: Submission, verdict: Verdict, now: datetime) -> FinalizedEvent:
    """The final status of a submission (only the ingestor sets it) and its event."""
    submission.status = verdict.status
    submission.verdict_detail = verdict.detail.model_dump(mode="json")
    submission.finished_at = now
    return finalized(submission)


def finalized(submission: Submission) -> FinalizedEvent:
    return FinalizedEvent(
        status=submission.status,  # type: ignore[arg-type]  # a final status, checked by the caller
        verdict_detail=VerdictDetail.model_validate(submission.verdict_detail or {}),
    )
