"""`POST /submissions`, `GET /submissions/{id}`. Phase 0 has no workers: submissions stay queued."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.core.db import get_session
from apparatica.core.errors import ApiError, ErrorCode, problem_responses
from apparatica.core.http import PRIVATE
from apparatica.submissions import service
from apparatica.submissions.schemas import Submission, SubmissionCreate

router = APIRouter(tags=["submissions"])

PHASE_0 = {"x-phase": 0}
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post(
    "/submissions",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Submission,
    responses=problem_responses(
        ErrorCode.NOT_FOUND,
        ErrorCode.PROBLEM_VERSION_OUTDATED,
        ErrorCode.CODE_TOO_LARGE,
        ErrorCode.VALIDATION_ERROR,
        ErrorCode.JUDGE_UNAVAILABLE,
    ),
    openapi_extra=PHASE_0,
)
async def create_submission(
    request: Request, response: Response, session: Session, body: SubmissionCreate
) -> Submission:
    """A Run or a Submit of the current version of a problem; the check runs in the background."""
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
    "/submissions/{id}",
    response_model=Submission,
    responses=problem_responses(ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR),
    openapi_extra=PHASE_0,
)
async def get_submission(response: Response, session: Session, id: uuid.UUID) -> Submission:
    """A submission with its stages and artifacts. Access by author arrives with guests (T1.7)."""
    submission = await service.get_submission(session, id)
    if submission is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"No submission {id}")
    response.headers["Cache-Control"] = PRIVATE
    return submission
