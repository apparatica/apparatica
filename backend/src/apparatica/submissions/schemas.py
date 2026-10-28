"""Request and response schemas of submissions (specs/05 §3, phases 0 and 1).

Stage summaries and verdict details are the models of the judge core: the API stores and shows
what the worker reports and the ingestor aggregates.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, PositiveInt, field_validator

from judge.core.package import Slug
from judge.core.stage import FailureKind, StageStatus, StageSummary, SubmissionKind
from judge.core.verdict import VerdictDetail

# specs/04 §3.1; the same values as SUBMISSION_STATUSES of the models (a test checks it).
SubmissionStatus = Literal[
    "queued",
    "running",
    "accepted",
    "accepted_with_warnings",
    "wrong_answer",
    "compile_error",
    "limit_exceeded",
    "forbidden_construct",
    "cancelled",
    "internal_error",
]


class SubmissionCreate(BaseModel):
    problem: Slug = Field(description="Slug of the problem")
    version: PositiveInt = Field(description="The current version, as the client shows it")
    kind: SubmissionKind
    code: str = Field(
        min_length=1, description="Size limits: GET /config, limits.solution (CODE_TOO_LARGE)"
    )
    captcha: str | None = Field(
        default=None,
        max_length=4096,
        description="Solved ALTCHA challenge (GET /captcha/challenge) after CAPTCHA_REQUIRED",
    )

    @field_validator("code")
    @classmethod
    def _storable(cls, code: str) -> str:
        # Postgres text cannot hold NUL; lone surrogates are not UTF-8.
        if "\x00" in code:
            raise ValueError("the code must not contain NUL characters")
        try:
            code.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("the code must be valid Unicode text") from None
        return code


class SubmissionStage(BaseModel):
    key: str = Field(examples=["sim_full"])
    type: str = Field(examples=["sim"])
    ordinal: int
    status: StageStatus
    failure_kind: FailureKind | None
    error_code: str | None = Field(description="Platform failure of status=error")
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    metrics_schema: str | None = Field(examples=["sim/v1"])
    metrics: dict[str, object]
    summary: StageSummary


# Artifacts a user can download (specs/07 §4.4); the testbench result file is never offered.
ArtifactKind = Literal["log", "events", "fst"]
ArtifactState = Literal["ready", "expired", "pending", "failed"]
WaveformScope = Literal["failure_window", "full_test"]


WaveformSignalRole = Literal["clock", "input", "output", "expected"]


class WaveformSignal(BaseModel):
    """A signal to show, in the order of the viewer (ADR-0004): the clock, the inputs, then every
    output followed by the value the model expected."""

    path: str = Field(description="Full name in the FST", examples=["tb_top.exp_rdata"])
    port: str = Field(description="Port of the problem interface", examples=["rdata"])
    role: WaveformSignalRole


class Waveform(BaseModel):
    """What an FST trace covers (ADR-0004)."""

    test: str = Field(description="Id of the traced test", examples=["t7"])
    scope: WaveformScope
    from_cycle: int
    to_cycle: int
    cursor_cycle: int | None = Field(description="Cycle of the first mismatch")
    cursor_time_ps: int | None = Field(
        description="FST time of the first mismatch in picoseconds: the axis of the viewer is"
        " in time, not in cycles"
    )
    signals: list[WaveformSignal] = Field(
        description="Empty for a trace recorded before the list existed: the viewer picks"
    )


class SubmissionArtifact(BaseModel):
    kind: ArtifactKind
    stage: str | None
    state: ArtifactState = Field(
        description="expired: removed by the retention rules (an FST can be recreated);"
        " pending, failed: an FST being recreated or not recreated"
        " (POST /submissions/{id}/waveform). One FST per stage: the latest"
    )
    size_bytes: int | None = Field(description="Null until the file exists")
    waveform: Waveform | None = Field(description="With kind=fst")


class WaveformRequest(BaseModel):
    scope: WaveformScope = Field(
        default="failure_window",
        description="full_test: the whole test, for signed-in users only (FR-WAV-05)",
    )
    test: str | None = Field(
        default=None, description="Test id for full_test; the failed test by default"
    )


class QuotaWindow(BaseModel):
    limit: int = Field(description="Per hour")
    remaining: int
    reset_at: datetime | None = Field(
        description="When one more becomes available; null while any are left"
    )


class QuotaStatus(BaseModel):
    """What is left of the quotas of the current guest or user (specs/07 §3)."""

    checks: QuotaWindow
    waveforms: QuotaWindow = Field(description="Recreated and full-test waveforms")


class SubmissionSummary(BaseModel):
    id: uuid.UUID
    problem: str = Field(description="Slug of the problem")
    problem_title: str
    version: int
    kind: SubmissionKind
    status: SubmissionStatus
    verdict_detail: VerdictDetail | None = Field(description="Set with the final status")
    created_at: datetime
    finished_at: datetime | None


class Submission(SubmissionSummary):
    code: str
    seed: str = Field(description="64-bit seed as a decimal string", examples=["41917"])
    toolchain_profile: str = Field(examples=["sv-2026.10.2"])
    queue_position: int | None = Field(description="Position in the queue while queued")
    eta_s: int | None = Field(description="Estimated wait in the queue, seconds")
    started_at: datetime | None
    stages: list[SubmissionStage] = Field(description="In pipeline order")
    artifacts: list[SubmissionArtifact]


class SubmissionCreated(Submission):
    quota: QuotaStatus | None = Field(
        description="After this submission; null while quotas are off"
    )


class SubmissionPage(BaseModel):
    """Own submissions, newest first."""

    items: list[SubmissionSummary]
    next_cursor: str | None = Field(description="Pass as cursor for the next page")
    quota: QuotaStatus | None = Field(description="Null while quotas are off")
