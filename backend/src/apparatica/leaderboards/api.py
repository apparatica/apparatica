"""Leaderboards, public solutions and reference solutions (specs/05 §3, phase 3): the contract,
stubs until T3.5 and T3.9."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query

from apparatica.core.errors import ApiError, ErrorCode, problem_responses
from apparatica.leaderboards.schemas import (
    GlobalLeaderboard,
    ProblemLeaderboard,
    ReferencePage,
    Solution,
    SolutionPage,
)

router = APIRouter()

PHASE_3 = {"x-phase": 3}
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


def _stub(task: str) -> ApiError:
    return ApiError(
        ErrorCode.NOT_IMPLEMENTED, f"Declared by the phase 3 contract; arrives in {task}"
    )


@router.get(
    "/problems/{slug}/leaderboard",
    tags=["leaderboards"],
    response_model=ProblemLeaderboard,
    responses=problem_responses(
        ErrorCode.NOT_IMPLEMENTED, ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR
    ),
    openapi_extra=PHASE_3,
)
async def get_problem_leaderboard(
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
) -> ProblemLeaderboard:
    """The leaderboard of a problem (FR-LB-01..04): one entry per author, the best accepted
    Submit in the current epoch on the default toolchain profile. NOT_FOUND: no such published
    problem or it has no leaderboard; VALIDATION_ERROR: `sort` names no column."""
    raise _stub("T3.5")


@router.get(
    "/problems/{slug}/solutions",
    tags=["solutions"],
    response_model=SolutionPage,
    responses=problem_responses(
        ErrorCode.NOT_IMPLEMENTED, ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR
    ),
    openapi_extra=PHASE_3,
)
async def list_problem_solutions(
    slug: SlugPath,
    sort: SortKey = "rank",
    page: Page = 1,
    per_page: PerPage = 20,
) -> SolutionPage:
    """Public solutions of a problem, every version, several per author (FR-SOL-03); `rank`
    orders them by the formula of the leaderboard. Code is not listed: GET /solutions/{id}."""
    raise _stub("T3.5")


@router.get(
    "/problems/{slug}/reference",
    tags=["solutions"],
    response_model=ReferencePage,
    responses=problem_responses(
        ErrorCode.NOT_IMPLEMENTED,
        ErrorCode.NOT_FOUND,
        ErrorCode.REFERENCE_LOCKED,
        ErrorCode.VALIDATION_ERROR,
    ),
    openapi_extra=PHASE_3,
)
async def get_reference(slug: SlugPath) -> ReferencePage:
    """Reference solutions of the current version (FR-REF-01). REFERENCE_LOCKED: visibility
    after_accepted and the visitor (user or guest) has no accepted Submit of the problem;
    NOT_FOUND: no references or they are hidden."""
    raise _stub("T3.5")


@router.get(
    "/solutions/{id}",
    tags=["solutions"],
    response_model=Solution,
    responses=problem_responses(
        ErrorCode.NOT_IMPLEMENTED, ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR
    ),
    openapi_extra=PHASE_3,
)
async def get_solution(id: uuid.UUID) -> Solution:
    """A public solution (FR-SOL-01, FR-SOL-02): metrics, author and place for everyone, the code
    after the visitor's own accepted Submit of the problem (`code_locked`). NOT_FOUND: no such
    submission, not public, hidden by a moderator or its author is hidden."""
    raise _stub("T3.5")


@router.get(
    "/leaderboard",
    tags=["leaderboards"],
    response_model=GlobalLeaderboard,
    responses=problem_responses(ErrorCode.NOT_IMPLEMENTED, ErrorCode.VALIDATION_ERROR),
    openapi_extra=PHASE_3,
)
async def get_global_leaderboard(page: Page = 1, per_page: PerPage = 20) -> GlobalLeaderboard:
    """Users by points for all time (FR-LB-05); `me` and `around_me` for a signed-in user."""
    raise _stub("T3.9")
