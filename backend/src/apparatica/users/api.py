"""The own account `/me` and public profiles `/users/{nick}` (specs/05 §3, phase 2): the contract,
stubs until T2.1a, T2.4 and T2.7-T2.9. Every `/me` route answers UNAUTHENTICATED without a session.
"""

from typing import Annotated

from fastapi import APIRouter, Path, status

from apparatica.auth.schemas import Me, Nick
from apparatica.core.errors import ApiError, ErrorCode, problem_responses
from apparatica.users.schemas import AccountExport, Draft, DraftSave, MeUpdate, Profile

router = APIRouter(tags=["users"])

PHASE_2 = {"x-phase": 2}
Slug = Annotated[str, Path(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=64)]


def _stub(task: str) -> ApiError:
    return ApiError(
        ErrorCode.NOT_IMPLEMENTED, f"Declared by the phase 2 contract; arrives in {task}"
    )


@router.get(
    "/me",
    response_model=Me,
    responses=problem_responses(ErrorCode.NOT_IMPLEMENTED, ErrorCode.UNAUTHENTICATED),
    openapi_extra=PHASE_2,
)
async def get_me() -> Me:
    """The signed-in user; UNAUTHENTICATED for a guest."""
    raise _stub("T2.1a")


@router.patch(
    "/me",
    response_model=Me,
    responses=problem_responses(
        ErrorCode.NOT_IMPLEMENTED,
        ErrorCode.UNAUTHENTICATED,
        ErrorCode.CSRF_FAILED,
        ErrorCode.NICK_TAKEN,
        ErrorCode.NICK_CHANGE_TOO_SOON,
        ErrorCode.VALIDATION_ERROR,
    ),
    openapi_extra=PHASE_2,
)
async def update_me(body: MeUpdate) -> Me:
    """Change the nick or the display name (FR-AUTH-02). NICK_CHANGE_TOO_SOON: `params.available_at`
    is when it may change again."""
    raise _stub("T2.4")


@router.delete(
    "/me",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Me,
    responses=problem_responses(
        ErrorCode.NOT_IMPLEMENTED, ErrorCode.UNAUTHENTICATED, ErrorCode.CSRF_FAILED
    ),
    openapi_extra=PHASE_2,
)
async def delete_me() -> Me:
    """Request deletion of the account in 7 days (FR-USR-05): `delete_at` is set, the profile is
    hidden at once, sessions stay so that POST /me/restore can cancel it. Repeating keeps the
    date."""
    raise _stub("T2.9")


@router.post(
    "/me/restore",
    response_model=Me,
    responses=problem_responses(
        ErrorCode.NOT_IMPLEMENTED, ErrorCode.UNAUTHENTICATED, ErrorCode.CSRF_FAILED
    ),
    openapi_extra=PHASE_2,
)
async def restore_me() -> Me:
    """Cancel a requested deletion; without one nothing changes."""
    raise _stub("T2.9")


@router.get(
    "/me/export",
    response_model=AccountExport,
    responses={
        200: {
            "description": "The data as an attachment",
            "headers": {"Content-Disposition": {"schema": {"type": "string"}}},
        },
        **problem_responses(
            ErrorCode.NOT_IMPLEMENTED, ErrorCode.UNAUTHENTICATED, ErrorCode.RATE_LIMITED
        ),
    },
    openapi_extra=PHASE_2,
)
async def export_me() -> AccountExport:
    """Own data with the code of every kept submission (FR-USR-05)."""
    raise _stub("T2.9")


@router.get(
    "/me/drafts/{slug}",
    response_model=Draft,
    responses=problem_responses(
        ErrorCode.NOT_IMPLEMENTED,
        ErrorCode.UNAUTHENTICATED,
        ErrorCode.NOT_FOUND,
        ErrorCode.VALIDATION_ERROR,
    ),
    openapi_extra=PHASE_2,
)
async def get_draft(slug: Slug) -> Draft:
    """The saved draft of a problem; NOT_FOUND: none (FR-EDT-02)."""
    raise _stub("T2.7")


@router.put(
    "/me/drafts/{slug}",
    response_model=Draft,
    responses=problem_responses(
        ErrorCode.NOT_IMPLEMENTED,
        ErrorCode.UNAUTHENTICATED,
        ErrorCode.CSRF_FAILED,
        ErrorCode.NOT_FOUND,
        ErrorCode.CODE_TOO_LARGE,
        ErrorCode.VALIDATION_ERROR,
        ErrorCode.RATE_LIMITED,
    ),
    openapi_extra=PHASE_2,
)
async def save_draft(slug: Slug, body: DraftSave) -> Draft:
    """Save the draft of a published problem; the last save wins. NOT_FOUND: no such problem."""
    raise _stub("T2.7")


@router.get(
    "/users/{nick}",
    response_model=Profile,
    responses=problem_responses(
        ErrorCode.NOT_IMPLEMENTED, ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR
    ),
    openapi_extra=PHASE_2,
)
async def get_profile(nick: Annotated[Nick, Path()]) -> Profile:
    """A public profile (FR-USR-04). NOT_FOUND also for a hidden account or one being deleted."""
    raise _stub("T2.8")
