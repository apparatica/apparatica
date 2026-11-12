"""Request and response schemas of submissions (specs/05 §3, phases 0 and 1).

Stage summaries and verdict details are the models of the judge core: the API stores and shows
what the worker reports and the ingestor aggregates.
"""

import uuid
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, PositiveInt, field_validator

from judge.core.package import Interface, Slug
from judge.core.stage import FailureKind, ParamSet, StageStatus, StageSummary, SubmissionKind
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


def param_sets_of(manifest: Mapping[str, Any]) -> Callable[[str | None], ParamSet | None]:
    """The set of a stored stage instance with its values (ADR-0014): `stage_results` keeps the
    id of the set, the values are those of the package of the problem version (`manifest`)."""
    interface = Interface.model_validate(manifest["interface"])

    def param_set(set_id: str | None) -> ParamSet | None:
        if set_id is None:
            return None
        return ParamSet(id=set_id, values=interface.param_set_values(set_id))

    return param_set


class SubmissionStage(BaseModel):
    key: str = Field(
        examples=["sim_full", "sim_full@narrow"],
        description="Key of the stage instance: the stage key, or `<stage key>@<set id>` at an"
        " extra parameter set (specs/06 §2)",
    )
    type: str = Field(examples=["sim"])
    ordinal: int
    param_set: ParamSet | None = Field(
        description="Set of a stage checked at several parameter sets (ADR-0014), the primary one"
        " included: the values show for hidden tests too; null: the stage runs at the primary set"
        " only"
    )
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
    scope: WaveformScope = Field(
        description="failure_window: around the first mismatch; full_test: the whole failed test"
    )
    from_cycle: int | None = Field(
        description="First traced cycle; null until the FST of a whole test is recorded"
    )
    to_cycle: int | None = Field(description="Last traced cycle; null with from_cycle")
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
        " (POST /submissions/{id}/waveform). Up to two FST per stage, one per waveform.scope:"
        " the latest of each"
    )
    size_bytes: int | None = Field(description="Null until the file exists")
    error_code: str | None = Field(
        description="With state=failed: why the FST was not recorded, e.g. TRACE_TOO_LARGE"
        " (a whole test above the FST limit of the problem)"
    )
    waveform: Waveform | None = Field(description="With kind=fst")


class WaveformRequest(BaseModel):
    scope: WaveformScope = Field(
        default="failure_window",
        description="full_test: the whole failed test of a Run (FR-WAV-05)",
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


class LeaderboardPlacement(BaseModel):
    """The place of the author in the leaderboard of the problem after an accepted Submit
    (FR-RUN-05, phase 3): the entry of the author is their best solution, this one or an earlier
    one."""

    rank: int = Field(
        ge=1, description="Equal metrics share a place (1, 2, 2, 4); a duplicate has its leader's"
    )
    total: int = Field(ge=1, description="Entries of the leaderboard, one per author")
    better_than: float = Field(
        ge=0, le=1, examples=[0.96], description="Share of the other entries ranked lower"
    )
    is_best: bool = Field(
        description="This submission is the entry of the author; false: an earlier solution of"
        " the author ranks higher and keeps the place"
    )
    duplicate_of: uuid.UUID | None = Field(
        description="Solution whose normalized syntax tree is the same and which was sent"
        " earlier: it holds the place (FR-LB-04)"
    )


class Submission(SubmissionSummary):
    code: str
    public: bool = Field(
        description="An accepted Submit of a signed-in user: others see it at /solutions/{id}"
        " (phase 3), unless a moderator hid it or its author"
    )
    leaderboard: LeaderboardPlacement | None = Field(
        description="With a final status: the place of the author if the submission entered the"
        " leaderboard (a ranked problem, signed-in author, current epoch, default toolchain"
        " profile, netlist simulation passed); null otherwise"
    )
    seed: str = Field(description="64-bit seed as a decimal string", examples=["41917"])
    toolchain_profile: str = Field(examples=["sv-2026.10.2"])
    waveview_url: str | None = Field(
        description="Page of the waveform viewer of this toolchain profile, for an isolated frame"
        " (ADR-0004); null: no viewer",
        examples=["https://waveview.apparatica.app/2026.10.1/index.html"],
    )
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
