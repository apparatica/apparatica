"""Leaderboards of problems and of users, public solutions and reference solutions (specs/05 §3,
phase 3).

An answer that depends on the visitor (their row, their access to code) is private for a
signed-in user or a guest with a cookie. The others are public but revalidated by their ETag on
every use: a leaderboard changes within seconds of an accepted Submit (FR-LB-06)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.auth.guests import Guest
from apparatica.auth.models import User
from apparatica.auth.sessions import CurrentSession
from apparatica.core.db import get_session
from apparatica.core.errors import ApiError, ErrorCode, problem_responses
from apparatica.core.http import PRIVATE, REVALIDATE, cached_json
from apparatica.leaderboards import boards, rating, solutions
from apparatica.leaderboards.boards import Board
from apparatica.leaderboards.schemas import (
    GlobalLeaderboard,
    ProblemLeaderboard,
    ReferencePage,
    Solution,
    SolutionPage,
)
from apparatica.leaderboards.solutions import Visitor
from apparatica.submissions.quotas import Author

router = APIRouter()

PHASE_3 = {"x-phase": 3}
Session = Annotated[AsyncSession, Depends(get_session)]
SlugPath = Annotated[str, Path(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=64)]
Page = Annotated[int, Query(ge=1)]
PerPage = Annotated[int, Query(ge=1, le=100)]
# `rank`: the places; `submitted_at` or a metric `<stage key>.<metric>` of `columns`; a leading
# `-` reverses. Sorting never changes the places (FR-LB-01).
SortKey = Annotated[
    str,
    Query(
        pattern=r"^(rank|-?submitted_at|-?[a-z_]+\.[a-z0-9_]+)$",
        max_length=64,
        description="rank, submitted_at or a metric of `columns`; a leading `-` reverses",
        examples=["rank", "-submitted_at", "synth.area_um2"],
    ),
]


async def current_visitor(session: Session, signed_in: CurrentSession, guest: Guest) -> Visitor:
    """The signed-in user with their role, else the guest of the cookie, else nobody."""
    if signed_in is None:
        return Visitor(Author(guest_id=guest))
    role = await session.scalar(select(User.role).where(User.id == signed_in.user_id))
    return Visitor(Author(user_id=signed_in.user_id), role)


CurrentVisitor = Annotated[Visitor, Depends(current_visitor)]


async def _board(session: AsyncSession, slug: str) -> Board:
    board = await boards.find_board(session, slug)
    if board is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"No published problem {slug!r}")
    return board


def _answer(request: Request, body: BaseModel, visitor: Visitor) -> Response:
    nobody = visitor.author.key is None
    response = cached_json(request, body, REVALIDATE if nobody else PRIVATE)
    response.headers["Vary"] = "Cookie"  # an answer for nobody must not be reused after a login
    return response


@router.get(
    "/problems/{slug}/leaderboard",
    tags=["leaderboards"],
    response_model=ProblemLeaderboard,
    responses=problem_responses(ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR),
    openapi_extra=PHASE_3,
)
async def get_problem_leaderboard(
    request: Request,
    session: Session,
    visitor: CurrentVisitor,
    slug: SlugPath,
    group: Annotated[
        bool, Query(description="Fold later solutions with the same syntax tree (FR-LB-04)")
    ] = True,
    around: Annotated[
        Literal["me"] | None,
        Query(description="me: the page with the entry of the signed-in user; `page` is ignored"),
    ] = None,
    sort: SortKey = "rank",
    page: Page = 1,
    per_page: PerPage = 20,
) -> Response:
    """The leaderboard of a problem (FR-LB-01..04): one entry per author, the best accepted
    Submit in the current epoch on the default toolchain profile. NOT_FOUND: no such published
    problem or it has no leaderboard; VALIDATION_ERROR: `sort` names no column."""
    board = await _board(session, slug)
    body = await boards.problem_leaderboard(
        session,
        board,
        viewer=visitor.user_id,
        group=group,
        around_me=around == "me",
        sort=sort,
        page=page,
        per_page=per_page,
    )
    return _answer(request, body, visitor)


@router.get(
    "/problems/{slug}/solutions",
    tags=["solutions"],
    response_model=SolutionPage,
    responses=problem_responses(ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR),
    openapi_extra=PHASE_3,
)
async def list_problem_solutions(
    request: Request,
    session: Session,
    visitor: CurrentVisitor,
    slug: SlugPath,
    sort: SortKey = "rank",
    page: Page = 1,
    per_page: PerPage = 20,
) -> Response:
    """Public solutions of a problem, every version, several per author (FR-SOL-03); `rank`
    orders them by the formula of the leaderboard, solutions without its metrics last. Code is
    not listed: GET /solutions/{id}. VALIDATION_ERROR: `sort` names no column."""
    board = await _board(session, slug)
    body = await solutions.list_solutions(
        session, board, visitor, sort=sort, page=page, per_page=per_page
    )
    return _answer(request, body, visitor)


@router.get(
    "/problems/{slug}/reference",
    tags=["solutions"],
    response_model=ReferencePage,
    responses=problem_responses(
        ErrorCode.NOT_FOUND, ErrorCode.REFERENCE_LOCKED, ErrorCode.VALIDATION_ERROR
    ),
    openapi_extra=PHASE_3,
)
async def get_reference(
    request: Request, session: Session, visitor: CurrentVisitor, slug: SlugPath
) -> Response:
    """Reference solutions of the current version (FR-REF-01). REFERENCE_LOCKED: visibility
    after_accepted and the visitor (user or guest) has no accepted Submit of the problem;
    NOT_FOUND: no references or they are hidden."""
    board = await _board(session, slug)
    body = await solutions.get_reference(session, board, visitor)
    return _answer(request, body, visitor)


@router.get(
    "/solutions/{id}",
    tags=["solutions"],
    response_model=Solution,
    responses=problem_responses(ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR),
    openapi_extra=PHASE_3,
)
async def get_solution(
    request: Request, session: Session, visitor: CurrentVisitor, id: uuid.UUID
) -> Response:
    """A public solution (FR-SOL-01, FR-SOL-02): metrics, author and place for everyone, the code
    after the visitor's own accepted Submit of the problem (`code_locked`); the author sees
    their own code. NOT_FOUND: no such submission, not public, or its problem is not published
    (hidden solutions and authors arrive with moderation, T3.12)."""
    body = await solutions.get_solution(session, id, visitor)
    if body is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"No public solution {id}")
    return _answer(request, body, visitor)


@router.get(
    "/leaderboard",
    tags=["leaderboards"],
    response_model=GlobalLeaderboard,
    responses=problem_responses(ErrorCode.VALIDATION_ERROR),
    openapi_extra=PHASE_3,
)
async def get_global_leaderboard(
    request: Request,
    session: Session,
    visitor: CurrentVisitor,
    page: Page = 1,
    per_page: PerPage = 20,
) -> Response:
    """Users by points for all time (FR-LB-05); `me` and `around_me` for a signed-in user."""
    body = await rating.global_leaderboard(
        session,
        request.app.state.platform.rating,
        viewer=visitor.user_id,
        page=page,
        per_page=per_page,
        today=datetime.now(UTC).date(),
    )
    return _answer(request, body, visitor)
