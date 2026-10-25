"""Request and response schemas of submissions (specs/05 §3, phase 0).

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


class SubmissionArtifact(BaseModel):
    kind: str = Field(examples=["log", "fst"])
    stage: str | None
    size_bytes: int
    expired: bool = Field(description="Removed by the retention rules; FST can be recreated")


class Submission(BaseModel):
    id: uuid.UUID
    problem: str = Field(description="Slug of the problem")
    problem_title: str
    version: int
    kind: SubmissionKind
    status: SubmissionStatus
    code: str
    seed: str = Field(description="64-bit seed as a decimal string", examples=["41917"])
    toolchain_profile: str = Field(examples=["sv-2026.10.2"])
    queue_position: int | None = Field(description="Position in the queue; from phase 1")
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    verdict_detail: VerdictDetail | None = Field(description="Set with the final status")
    stages: list[SubmissionStage] = Field(description="In pipeline order")
    artifacts: list[SubmissionArtifact]
