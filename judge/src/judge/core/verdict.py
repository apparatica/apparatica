"""Verdict aggregation (specs/04 §3.3): used by the CLI and the ingestor, not by the worker."""

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from judge.core.stage import FailureKind, LimitKind, StageResult

SubmissionStatus = Literal[
    "accepted",
    "accepted_with_warnings",
    "wrong_answer",
    "compile_error",
    "limit_exceeded",
    "forbidden_construct",
    "cancelled",
    "internal_error",
]

_BY_FAILURE: dict[FailureKind, SubmissionStatus] = {
    "forbidden": "forbidden_construct",
    "compile": "compile_error",
    "wrong": "wrong_answer",
    "limit": "limit_exceeded",
}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FirstFailure(_Model):
    stage: str
    test: str | None = None
    cycle: int | None = None


class VerdictDetail(_Model):
    first_failure: FirstFailure | None = None
    limit: LimitKind | None = None
    warnings: list[str] = []  # keys of stages with warnings
    error_codes: list[str] = []


class Verdict(_Model):
    status: SubmissionStatus
    detail: VerdictDetail = VerdictDetail()


def aggregate(results: Sequence[StageResult], *, cancelled: bool = False) -> Verdict:
    """Cancellation first (it may break a stage with an error), then platform errors, then the
    first failed stage in pipeline order, then warnings."""
    if cancelled or any(r.status == "cancelled" for r in results):
        return Verdict(status="cancelled")
    errors = [r for r in results if r.status == "error"]
    if errors:
        codes = [r.error_code for r in errors if r.error_code]
        return Verdict(status="internal_error", detail=VerdictDetail(error_codes=codes))
    failed = next(
        (r for r in sorted(results, key=lambda r: r.ordinal) if r.status == "failed"), None
    )
    if failed is not None:
        assert failed.failure_kind is not None
        test = next((t for t in failed.summary.tests if t.status == "failed"), None)
        first = FirstFailure(
            stage=failed.key, test=test.id if test else None, cycle=test.cycle if test else None
        )
        detail = VerdictDetail(first_failure=first, limit=failed.limit)
        return Verdict(status=_BY_FAILURE[failed.failure_kind], detail=detail)
    warnings = [r.key for r in results if r.status == "warning"]
    if warnings:
        return Verdict(status="accepted_with_warnings", detail=VerdictDetail(warnings=warnings))
    return Verdict(status="accepted")
