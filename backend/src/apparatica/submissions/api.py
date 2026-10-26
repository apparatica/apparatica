"""Submissions (specs/05 §3). `POST` and `GET /submissions/{id}` work since phase 0 (no workers yet:
submissions stay queued); the other routes are the phase 1 contract, stubs until implemented."""

import uuid
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.core.db import get_session
from apparatica.core.errors import ApiError, ErrorCode, problem_responses
from apparatica.core.http import PRIVATE, EventStreamResponse
from apparatica.submissions import service
from apparatica.submissions.events import SubmissionEvent
from apparatica.submissions.live import archived_events, live_events
from apparatica.submissions.schemas import (
    ArtifactKind,
    Submission,
    SubmissionArtifact,
    SubmissionCreate,
    SubmissionCreated,
    SubmissionPage,
    WaveformRequest,
)
from judge.core.jobs import submission_stream_key
from judge.core.package import Slug

router = APIRouter(tags=["submissions"])

PHASE_0 = {"x-phase": 0}
PHASE_1 = {"x-phase": 1}
Session = Annotated[AsyncSession, Depends(get_session)]
# A Valkey stream entry id: the SSE `id:` of an event.
EventId = Annotated[str, Query(pattern=r"^\d+-\d+$")]


def not_implemented(task: str) -> NoReturn:
    raise ApiError(
        ErrorCode.NOT_IMPLEMENTED, f"Declared by the phase 1 contract; arrives in {task}"
    )


@router.post(
    "/submissions",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SubmissionCreated,
    responses=problem_responses(
        ErrorCode.NOT_FOUND,
        ErrorCode.PROBLEM_VERSION_OUTDATED,
        ErrorCode.CODE_TOO_LARGE,
        ErrorCode.HEAVY_NOT_ALLOWED,
        ErrorCode.VALIDATION_ERROR,
        ErrorCode.CAPTCHA_REQUIRED,
        ErrorCode.RATE_LIMITED,
        ErrorCode.JUDGE_UNAVAILABLE,
    ),
    openapi_extra=PHASE_0,
)
async def create_submission(
    request: Request, response: Response, session: Session, body: SubmissionCreate
) -> SubmissionCreated:
    """A Run or a Submit of the current version of a problem; the check runs in the background.
    CAPTCHA_REQUIRED: solve GET /captcha/challenge and repeat with `captcha`."""
    state = request.app.state
    submission = await service.create_submission(
        session,
        body,
        limits=state.platform.limits.solution,
        tokens=state.job_tokens,
        queue=state.job_queue,
    )
    response.headers["Location"] = str(request.url_for("get_submission", id=submission.id))
    response.headers["Cache-Control"] = PRIVATE
    return submission


@router.get(
    "/submissions",
    response_model=SubmissionPage,
    responses=problem_responses(ErrorCode.VALIDATION_ERROR, ErrorCode.NOT_IMPLEMENTED),
    openapi_extra=PHASE_1,
)
async def list_submissions(
    problem: Annotated[Slug | None, Query(description="Slug of a problem")] = None,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SubmissionPage:
    """Own submissions (the guest by cookie) and the quotas left."""
    not_implemented("T1.7")


@router.get(
    "/submissions/{id}",
    response_model=Submission,
    responses=problem_responses(ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR),
    openapi_extra=PHASE_0,
)
async def get_submission(
    request: Request, response: Response, session: Session, id: uuid.UUID
) -> Submission:
    """A submission with its stages and artifacts. Access by author arrives with guests (T1.7)."""
    submission = await service.get_submission(session, id, request.app.state.job_queue)
    if submission is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"No submission {id}")
    response.headers["Cache-Control"] = PRIVATE
    return submission


@router.get(
    "/submissions/{id}/events",
    response_class=EventStreamResponse,
    responses={
        200: {
            "model": SubmissionEvent,
            "description": "Server-Sent Events: `data:` is a SubmissionEvent, `event:` its type,"
            " `id:` the stream entry id. `: keepalive` comments every 15 s.",
        },
        **problem_responses(
            ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR, ErrorCode.JUDGE_UNAVAILABLE
        ),
    },
    openapi_extra=PHASE_1,
)
async def stream_submission_events(
    request: Request,
    session: Session,
    id: uuid.UUID,
    from_: Annotated[
        EventId | None, Query(alias="from", description="Continue after this event id")
    ] = None,
    last_event_id: Annotated[
        str | None,
        Header(
            alias="Last-Event-ID",
            pattern=r"^\d+-\d+$",
            description="Set by EventSource on reconnect",
        ),
    ] = None,
) -> EventStreamResponse:
    """The live log and progress of a check (specs/07 §4); after the stream expires, the same
    events from the archive. The status is final only with the `finalized` event. While the check
    waits, `queue` events carry its position; they have no `id:`."""
    watched = await service.watch_submission(session, id)
    if watched is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"No submission {id}")
    after = last_event_id or from_ or "0-0"
    state = request.app.state
    hub = state.stream_hub
    if watched.final and (hub is None or not await hub.exists(submission_stream_key(id))):
        body = archived_events(watched, after, state.storage, state.settings.s3_bucket_artifacts)
    elif hub is None:
        raise ApiError(ErrorCode.JUDGE_UNAVAILABLE, "The streams of checks are unavailable")
    else:
        body = live_events(watched, after, hub, state.job_queue)
    # No proxy buffering: events must reach the browser as they come (specs/07 §4.2).
    return EventStreamResponse(body, headers={"Cache-Control": PRIVATE, "X-Accel-Buffering": "no"})


@router.post(
    "/submissions/{id}/cancel",
    status_code=status.HTTP_202_ACCEPTED,
    response_class=Response,
    responses={
        202: {"description": "Cancellation requested"},
        **problem_responses(
            ErrorCode.NOT_FOUND,
            ErrorCode.SUBMISSION_FINISHED,
            ErrorCode.VALIDATION_ERROR,
            ErrorCode.NOT_IMPLEMENTED,
        ),
    },
    openapi_extra=PHASE_1,
)
async def cancel_submission(id: uuid.UUID) -> None:
    """Cancel a queued or running check; the result comes as `finalized` with `cancelled`."""
    not_implemented("T1.6")


@router.get(
    "/submissions/{id}/artifacts/{kind}",
    status_code=status.HTTP_302_FOUND,
    response_class=RedirectResponse,
    responses={
        302: {
            "description": "Redirect to a presigned URL of the file (attachment)",
            "headers": {"Location": {"schema": {"type": "string", "format": "uri"}}},
        },
        **problem_responses(
            ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR, ErrorCode.NOT_IMPLEMENTED
        ),
    },
    openapi_extra=PHASE_1,
)
async def get_artifact(
    id: uuid.UUID,
    kind: ArtifactKind,
    stage: Annotated[str | None, Query(max_length=64, description="Key of the stage")] = None,
) -> RedirectResponse:
    """Download an artifact of a submission; NOT_FOUND also when it has expired."""
    not_implemented("T1.2b")


@router.post(
    "/submissions/{id}/waveform",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SubmissionArtifact,
    responses=problem_responses(
        ErrorCode.NOT_FOUND,
        ErrorCode.UNAUTHENTICATED,
        ErrorCode.VALIDATION_ERROR,
        ErrorCode.RATE_LIMITED,
        ErrorCode.NOT_IMPLEMENTED,
    ),
    openapi_extra=PHASE_1,
)
async def request_waveform(id: uuid.UUID, body: WaveformRequest) -> SubmissionArtifact:
    """Recreate an expired FST or record a whole test with the seed of the submission
    (FR-WAV-05); the FST artifact is pending until GET /submissions/{id} shows it ready."""
    not_implemented("T1.17")
