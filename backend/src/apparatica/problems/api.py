"""`GET /problems`, `/problems/{slug}`, `/problems/{slug}/versions/{version}`, `/tags` (phase 0);
pictures of statements `/problems/{slug}/versions/{version}/assets/{path}` (phase 1)."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.core.db import get_session
from apparatica.core.errors import ApiError, ErrorCode, problem_responses
from apparatica.core.http import IMMUTABLE, cached_bytes, cached_json
from apparatica.problems import service
from apparatica.problems.assets import PICTURES, picture_type
from apparatica.problems.schemas import (
    ProblemDetail,
    ProblemPage,
    ProblemVersionDetail,
    Sort,
    Tag,
)

router = APIRouter(tags=["problems"])

PHASE_0 = {"x-phase": 0}
PHASE_1 = {"x-phase": 1}
Session = Annotated[AsyncSession, Depends(get_session)]
SlugPath = Annotated[str, Path(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=64)]
ASSET_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    "X-Content-Type-Options": "nosniff",
}


@router.get(
    "/tags",
    response_model=list[Tag],
    openapi_extra=PHASE_0,
)
async def list_tags(request: Request, session: Session) -> Response:
    tags = await service.list_tags(session)
    return cached_json(request, tags)


@router.get(
    "/problems",
    response_model=ProblemPage,
    responses=problem_responses(ErrorCode.VALIDATION_ERROR),
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
    per_page: Annotated[
        int | None, Query(ge=1, le=100, description="catalog.per_page of GET /config if unset")
    ] = None,
) -> Response:
    platform = request.app.state.platform
    levels = [level.key for level in platform.difficulties]
    body = await service.list_problems(
        session,
        levels,
        difficulties=difficulty,
        tags=tag,
        q=q,
        sort=sort,
        page=page,
        per_page=per_page or platform.catalog.per_page,
    )
    return cached_json(request, body)


@router.get(
    "/problems/{slug}",
    response_model=ProblemDetail,
    responses=problem_responses(ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR),
    openapi_extra=PHASE_0,
)
async def get_problem(request: Request, session: Session, slug: SlugPath) -> Response:
    """The current version of a published problem and its acceptance rate."""
    problem = await service.get_problem(session, slug)
    if problem is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"No published problem {slug!r}")
    return cached_json(request, problem)


@router.get(
    "/problems/{slug}/versions/{version}",
    response_model=ProblemVersionDetail,
    responses=problem_responses(ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR),
    openapi_extra=PHASE_0,
)
async def get_problem_version(
    request: Request, session: Session, slug: SlugPath, version: Annotated[int, Path(ge=1)]
) -> Response:
    """A version up to the current one; its data never changes, so it is cached for a year (the
    acceptance rate, which changes, is only in `GET /problems/{slug}`)."""
    problem = await service.get_problem_version(session, slug, version)
    if problem is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"No published version {version} of {slug!r}")
    return cached_json(request, problem, IMMUTABLE)


@router.get(
    "/problems/{slug}/versions/{version}/assets/{path:path}",
    response_class=Response,
    responses={
        200: {
            "description": "The picture",
            "content": {
                media_type: {"schema": {"type": "string", "format": "binary"}}
                for media_type in sorted(set(PICTURES.values()))
            },
        },
        **problem_responses(ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR),
    },
    openapi_extra=PHASE_1,
)
async def get_problem_asset(
    request: Request,
    session: Session,
    slug: SlugPath,
    version: Annotated[int, Path(ge=1)],
    path: Annotated[str, Path(max_length=255, description="Under assets/ of the package")],
) -> Response:
    """A picture of the statement of a version, `assets/<path>` of its package (FR-PRB-03). Like
    the version, it never changes. A sandboxed CSP keeps an SVG opened by itself from running
    scripts on the origin of the site."""
    asset = f"assets/{path}"
    media_type = picture_type(asset)
    key = None if media_type is None else await service.asset_key(session, slug, version, asset)
    state = request.app.state
    data = None
    if key is not None:
        data = await asyncio.to_thread(state.storage.find, state.settings.s3_bucket_packages, key)
    if data is None or media_type is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"No picture {asset} in version {version} of {slug!r}")
    return cached_bytes(request, data, media_type, IMMUTABLE, ASSET_HEADERS)
