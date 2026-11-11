"""Submissions (specs/05 §3). The author is the signed-in user, else the guest of the `ap_guest`
cookie, which the first submission of a guest sets (FR-GST-01); a submission of someone else is
NOT_FOUND."""

import uuid
from dataclasses import replace
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.auth.guests import Guest
from apparatica.auth.sessions import CurrentSession
from apparatica.auth.throttle import throttle
from apparatica.core.db import get_session
from apparatica.core.errors import ApiError, ErrorCode, problem_responses
from apparatica.core.http import PRIVATE, EventStreamResponse
from apparatica.submissions import artifacts, service
from apparatica.submissions.events import SubmissionEvent
from apparatica.submissions.live import archived_events, live_events
from apparatica.submissions.quotas import Author
from apparatica.submissions.schemas import (
    ArtifactKind,
    Submission,
    SubmissionArtifact,
    SubmissionCreate,
    SubmissionCreated,
    SubmissionPage,
    SubmissionStatus,
    WaveformRequest,
    WaveformScope,
)
from judge.core.jobs import submission_stream_key
from judge.core.package import Slug

router = APIRouter(tags=["submissions"])

PHASE_0 = {"x-phase": 0}
PHASE_1 = {"x-phase": 1}
Session = Annotated[AsyncSession, Depends(get_session)]
# A Valkey stream entry id: the SSE `id:` of an event.
EventId = Annotated[str, Query(pattern=r"^\d+-\d+$")]


async def _submission_id(id: uuid.UUID) -> uuid.UUID:
    """The submission of the path, bound to every log record of the request (NFR-OBS-01)."""
    structlog.contextvars.bind_contextvars(submission_id=str(id))
    return id


SubmissionId = Annotated[uuid.UUID, Depends(_submission_id)]


async def current_author(request: Request, guest: Guest, session: CurrentSession) -> Author:
    """The author of the request: the signed-in user, else the guest of the cookie, if any."""
    address = request.app.state.client_addresses.hash(request)
    if session is not None:
        return Author(user_id=session.user_id, address=address)
    return Author(guest_id=guest, address=address)


CurrentAuthor = Annotated[Author, Depends(current_author)]


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
        ErrorCode.CSRF_FAILED,
        ErrorCode.CAPTCHA_REQUIRED,
        ErrorCode.RATE_LIMITED,
        ErrorCode.JUDGE_UNAVAILABLE,
    ),
    dependencies=[Depends(throttle)],
    openapi_extra=PHASE_0,
)
async def create_submission(
    request: Request,
    response: Response,
    session: Session,
    body: SubmissionCreate,
    author: CurrentAuthor,
) -> SubmissionCreated:
    """A Run or a Submit of the current version of a problem; the check runs in the background.
    Sets the guest cookie with the first submission of a guest. RATE_LIMITED: `params.quota`
    names the spent quota (docs/api.md). CAPTCHA_REQUIRED (guests only): solve
    GET /captcha/challenge and repeat with `captcha`."""
    state = request.app.state
    new_guest = uuid.uuid4() if author.key is None else None
    if new_guest is not None:
        author = replace(author, guest_id=new_guest)
    submission = await service.create_submission(
        session,
        body,
        limits=state.platform.limits.solution,
        tokens=state.job_tokens,
        queue=state.job_queue,
        quotas=state.quotas,
        captcha=state.captcha,
        author=author,
        waveview=state.settings.waveview_url,
    )
    structlog.contextvars.bind_contextvars(submission_id=str(submission.id))
    if new_guest is not None:
        state.guest_cookies.set(response, new_guest)
    response.headers["Location"] = str(request.url_for("get_submission", id=submission.id))
    response.headers["Cache-Control"] = PRIVATE
    return submission


@router.get(
    "/submissions",
    response_model=SubmissionPage,
    responses=problem_responses(ErrorCode.VALIDATION_ERROR),
    openapi_extra=PHASE_1,
)
async def list_submissions(
    request: Request,
    response: Response,
    session: Session,
    author: CurrentAuthor,
    problem: Annotated[Slug | None, Query(description="Slug of a problem")] = None,
    status: Annotated[
        list[SubmissionStatus],
        Query(description="Any of these statuses (FR-USR-03)"),
    ] = [],  # noqa: B006
    cursor: Annotated[str | None, Query(max_length=256)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SubmissionPage:
    """Own submissions, newest first, and the quotas left: of the signed-in user, else of the
    guest by cookie; empty without either."""
    items, next_cursor = await service.list_submissions(
        session, author, problem=problem, statuses=status, cursor=cursor, limit=limit
    )
    response.headers["Cache-Control"] = PRIVATE
    return SubmissionPage(
        items=items,
        next_cursor=next_cursor,
        quota=await request.app.state.quotas.status(session, author),
    )


@router.get(
    "/submissions/{id}",
    response_model=Submission,
    responses=problem_responses(ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR),
    openapi_extra=PHASE_0,
)
async def get_submission(
    request: Request, response: Response, session: Session, author: CurrentAuthor, id: SubmissionId
) -> Submission:
    """A submission of the caller with its stages and artifacts."""
    state = request.app.state
    submission = await service.get_submission(
        session,
        id,
        state.job_queue,
        author,
        placement_of=state.placement_of,
        waveview=state.settings.waveview_url,
    )
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
    author: CurrentAuthor,
    id: SubmissionId,
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
    watched = await service.watch_submission(session, id, author, request.app.state.placement_of)
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
            ErrorCode.CSRF_FAILED,
            ErrorCode.RATE_LIMITED,
            ErrorCode.JUDGE_UNAVAILABLE,
        ),
    },
    dependencies=[Depends(throttle)],
    openapi_extra=PHASE_1,
)
async def cancel_submission(
    request: Request, session: Session, author: CurrentAuthor, id: SubmissionId
) -> None:
    """Cancel a queued or running check of the caller; the result comes as `finalized` with
    `cancelled`."""
    await service.cancel_submission(session, id, request.app.state.job_queue, author)


@router.get(
    "/submissions/{id}/artifacts/{kind}",
    status_code=status.HTTP_302_FOUND,
    response_class=RedirectResponse,
    responses={
        302: {
            "description": "Redirect to a presigned URL of the file (attachment)",
            "headers": {"Location": {"schema": {"type": "string", "format": "uri"}}},
        },
        **problem_responses(ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR),
    },
    openapi_extra=PHASE_1,
)
async def get_artifact(
    request: Request,
    session: Session,
    author: CurrentAuthor,
    id: SubmissionId,
    kind: ArtifactKind,
    stage: Annotated[
        str | None,
        Query(max_length=64, description="Key of the stage instance", examples=["sim_full@narrow"]),
    ] = None,
    scope: Annotated[
        WaveformScope, Query(description="Which FST of the stage: the window or the whole test")
    ] = "failure_window",
) -> RedirectResponse:
    """Download the latest file of an artifact of the caller's submission: `stage` names the
    stage of a log or an FST, events have none. NOT_FOUND also when it has expired."""
    state = request.app.state
    settings = state.settings
    url = await artifacts.download_url(
        session,
        state.storage,
        bucket=settings.s3_bucket_artifacts,
        ttl_s=settings.artifact_url_ttl_s,
        submission_id=id,
        kind=kind,
        stage=stage,
        scope=scope,
        author=author,
    )
    headers = {"Cache-Control": PRIVATE}
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND, headers=headers)


@router.post(
    "/submissions/{id}/waveform",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SubmissionArtifact,
    responses=problem_responses(
        ErrorCode.NOT_FOUND,
        ErrorCode.VALIDATION_ERROR,
        ErrorCode.CSRF_FAILED,
        ErrorCode.RATE_LIMITED,
        ErrorCode.JUDGE_UNAVAILABLE,
    ),
    dependencies=[Depends(throttle)],
    openapi_extra=PHASE_1,
)
async def request_waveform(
    request: Request,
    session: Session,
    author: CurrentAuthor,
    id: SubmissionId,
    body: WaveformRequest,
) -> SubmissionArtifact:
    """Record an FST with the seed of the submission (FR-WAV-05): the expired failure window
    again, or the whole failed test of a Run (`full_test`), for guests and users alike. It is
    pending until GET /submissions/{id} shows it ready or failed. A kept or pending FST is
    answered as it is, without spending the quota. NOT_FOUND: no such submission, no trace
    window in it, or `full_test` of a Submit; RATE_LIMITED: `params.quota` is `waveforms`."""
    state = request.app.state
    return await artifacts.request_waveform(
        session,
        id,
        body,
        author=author,
        tokens=state.job_tokens,
        queue=state.job_queue,
        quotas=state.quotas,
    )
