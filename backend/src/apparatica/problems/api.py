"""`GET /problems`, `/problems/{slug}`, `/problems/{slug}/versions/{version}`, `/tags` (phase 0)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.core.db import get_session
from apparatica.core.errors import ApiError, ErrorCode, problem_responses
from apparatica.core.http import IMMUTABLE, cached_json
from apparatica.problems import service
from apparatica.problems.schemas import ProblemDetail, ProblemPage, Sort, Tag

router = APIRouter(tags=["problems"])

PHASE_0 = {"x-phase": 0}
Session = Annotated[AsyncSession, Depends(get_session)]
SlugPath = Annotated[str, Path(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=64)]


@router.get(
    "/tags",
    response_model=list[Tag],
    responses=problem_responses(ErrorCode.INTERNAL),
    openapi_extra=PHASE_0,
)
async def list_tags(request: Request, session: Session) -> Response:
    tags = await service.list_tags(session)
    return cached_json(request, tags)


@router.get(
    "/problems",
    response_model=ProblemPage,
    responses=problem_responses(ErrorCode.VALIDATION_ERROR, ErrorCode.INTERNAL),
    openapi_extra=PHASE_0,
)
async def list_problems(
    request: Request,
    session: Session,
    difficulty: Annotated[list[str], Query(description="Any of these levels")] = [],  # noqa: B006
    tag: Annotated[list[str], Query(description="Any of these tags")] = [],  # noqa: B006
    q: Annotated[str | None, Query(max_length=100, description="In the title or tags")] = None,
    sort: Sort = "number",
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 12,
) -> Response:
    levels = [level.key for level in request.app.state.platform.difficulties]
    body = await service.list_problems(
        session,
        levels,
        difficulties=difficulty,
        tags=tag,
        q=q,
        sort=sort,
        page=page,
        per_page=per_page,
    )
    return cached_json(request, body)


@router.get(
    "/problems/{slug}",
    response_model=ProblemDetail,
    responses=problem_responses(
        ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR, ErrorCode.INTERNAL
    ),
    openapi_extra=PHASE_0,
)
async def get_problem(request: Request, session: Session, slug: SlugPath) -> Response:
    """The current version of a published problem."""
    problem = await service.get_problem(session, slug)
    if problem is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"No published problem {slug!r}")
    return cached_json(request, problem)


@router.get(
    "/problems/{slug}/versions/{version}",
    response_model=ProblemDetail,
    responses=problem_responses(
        ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR, ErrorCode.INTERNAL
    ),
    openapi_extra=PHASE_0,
)
async def get_problem_version(
    request: Request, session: Session, slug: SlugPath, version: Annotated[int, Path(ge=1)]
) -> Response:
    """A version up to the current one; its data never changes, so it is cached for a year."""
    problem = await service.get_problem(session, slug, version)
    if problem is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"No published version {version} of {slug!r}")
    return cached_json(request, problem, IMMUTABLE)
