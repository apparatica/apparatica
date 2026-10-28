"""Tables of submissions, their stage results and artifacts, toolchain profiles (specs/04 §4).

Results are stored generically (specs/04 §1): a new stage adds a `stage_type` and a metrics
schema, not columns. Status values come from the judge core, which aggregates the verdict.
"""

import uuid
from datetime import datetime
from typing import Any, get_args

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from apparatica.core.db import Base, created_at, uuid_pk
from judge.core.stage import FailureKind, StageStatus, SubmissionKind
from judge.core.verdict import SubmissionStatus

# specs/04 §3.1: the verdicts of the judge preceded by the states before the verdict.
SUBMISSION_STATUSES: tuple[str, ...] = ("queued", "running", *get_args(SubmissionStatus))
STAGE_STATUSES: tuple[str, ...] = get_args(StageStatus)


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


class ToolchainProfile(Base):
    __tablename__ = "toolchain_profiles"
    __table_args__ = (
        # New submissions of a language are checked with its default profile.
        Index(
            "uq_toolchain_profiles_language_default",
            "language",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    id: Mapped[str] = mapped_column(primary_key=True)  # e.g. sv-2026.10
    language: Mapped[str]
    image: Mapped[str]
    image_digest: Mapped[str]
    tools: Mapped[dict[str, Any]]  # tool versions
    liberty: Mapped[str | None]  # the synthesis library, from Ф3
    # WAVEVIEW_VERSION of the viewer of its traces (ADR-0004): FST format and Surfer move together.
    waveview: Mapped[str | None]
    normalization_version: Mapped[int]
    is_default: Mapped[bool] = mapped_column(server_default="false")
    created_at: Mapped[datetime] = created_at()


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        CheckConstraint(_one_of("kind", get_args(SubmissionKind)), name="kind"),
        CheckConstraint("seed >= 0", name="seed_non_negative"),
        CheckConstraint("attempt > 0", name="attempt_positive"),
        Index("ix_submissions_guest_id_created_at", "guest_id", text("created_at DESC")),
        Index("ix_submissions_problem_version_id_status", "problem_version_id", "status"),
        Index("ix_submissions_ast_hash", "ast_hash"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    problem_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problem_versions.id"))
    guest_id: Mapped[uuid.UUID | None]
    kind: Mapped[str]
    code: Mapped[str]  # as sent by the user
    code_hash: Mapped[str | None]  # sha256 of the canonical text, the cache key
    ast_hash: Mapped[str | None]
    seed: Mapped[int] = mapped_column(BigInteger)
    toolchain_profile_id: Mapped[str] = mapped_column(ForeignKey("toolchain_profiles.id"))
    status: Mapped[str] = mapped_column(
        Enum(*SUBMISSION_STATUSES, name="submission_status"), server_default="queued"
    )
    verdict_detail: Mapped[dict[str, Any] | None]
    queue_class: Mapped[str]
    attempt: Mapped[int] = mapped_column(server_default="1")
    created_at: Mapped[datetime] = created_at()
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    client_ip_hash: Mapped[str | None]


class StageResult(Base):
    """Upserted by the ingestor on (submission_id, stage_key): redelivery is idempotent."""

    __tablename__ = "stage_results"
    __table_args__ = (
        UniqueConstraint("submission_id", "stage_key"),  # stage keys are unique in a pipeline
        CheckConstraint("ordinal >= 0", name="ordinal_non_negative"),
        CheckConstraint("duration_ms >= 0", name="duration_ms_non_negative"),
        CheckConstraint(_one_of("failure_kind", get_args(FailureKind)), name="failure_kind"),
        # specs/04 §3.3: a failed stage reports why, and only a failed one does.
        CheckConstraint(
            "(status = 'failed') = (failure_kind IS NOT NULL)", name="failure_kind_iff_failed"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE")
    )
    stage_key: Mapped[str]
    stage_type: Mapped[str]
    ordinal: Mapped[int]
    status: Mapped[str] = mapped_column(Enum(*STAGE_STATUSES, name="stage_status"))
    failure_kind: Mapped[str | None]
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    duration_ms: Mapped[int | None]
    metrics: Mapped[dict[str, Any] | None]
    metrics_schema: Mapped[str | None]  # e.g. sim/v1
    summary: Mapped[dict[str, Any] | None]  # tests, diagnostics, skip reason
    error_code: Mapped[str | None]


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="size_bytes_non_negative"),
        # What the retention task of the ingestor has yet to delete.
        Index(
            "ix_artifacts_expires_at_unpurged",
            "expires_at",
            postgresql_where=text("expires_at IS NOT NULL AND purged_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    stage_key: Mapped[str | None]
    kind: Mapped[str]  # log, events, fst, tb_result, ...
    storage_key: Mapped[str] = mapped_column(unique=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str]
    expires_at: Mapped[datetime | None]
    purged_at: Mapped[datetime | None]  # the file was deleted when it expired; the row stays
    created_at: Mapped[datetime] = created_at()


WAVEFORM_STATUSES = ("pending", "ready", "failed")


class Waveform(Base):
    """A trace window recorded again after its FST expired (FR-WAV-05): a job of the worker that
    ends with an FST artifact (`ready`) or without one (`failed`)."""

    __tablename__ = "waveforms"
    __table_args__ = (
        CheckConstraint(_one_of("status", WAVEFORM_STATUSES), name="status_known"),
        CheckConstraint(
            "(status = 'ready') = (artifact_id IS NOT NULL)", name="artifact_iff_ready"
        ),
        # One job at a time per traced stage: a repeated request finds the pending one.
        Index(
            "uq_waveforms_pending",
            "submission_id",
            "stage_key",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    stage_key: Mapped[str]
    status: Mapped[str] = mapped_column(server_default="pending")
    error_code: Mapped[str | None]
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = created_at()
    finished_at: Mapped[datetime | None]
