"""The own account `/me` and public profiles `/users/{nick}` (specs/05 §3, phase 2). Every `/me`
route answers UNAUTHENTICATED without a session.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.auth.accounts import ask_deletion, change_nick, me
from apparatica.auth.models import User
from apparatica.auth.schemas import Me, Nick
from apparatica.auth.sessions import SignedIn
from apparatica.auth.throttle import draft_throttle, throttle
from apparatica.core.db import get_session
from apparatica.core.errors import ApiError, ErrorCode, problem_responses
from apparatica.core.http import PRIVATE, cached_json
from apparatica.leaderboards.schemas import UserSolutionPage
from apparatica.leaderboards.solutions import user_solutions
from apparatica.users import drafts, profiles
from apparatica.users.export import export_account
from apparatica.users.schemas import AccountExport, Draft, DraftSave, MeUpdate, Profile

router = APIRouter(tags=["users"])

PHASE_2 = {"x-phase": 2}
PHASE_3 = {"x-phase": 3}
Slug = Annotated[str, Path(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=64)]
Session = Annotated[AsyncSession, Depends(get_session)]


async def _locked(session: AsyncSession, signed_in: SignedIn) -> User:
    user = await session.scalar(select(User).where(User.id == signed_in.user_id).with_for_update())
    if user is None:  # deleted after the lookup of the session
        raise ApiError(ErrorCode.UNAUTHENTICATED, "Sign in to continue")
    return user


@router.get(
    "/me",
    response_model=Me,
    responses=problem_responses(ErrorCode.UNAUTHENTICATED),
    openapi_extra=PHASE_2,
)
async def get_me(signed_in: SignedIn, session: Session) -> Me:
    """The signed-in user; UNAUTHENTICATED for a guest."""
    user = await session.get(User, signed_in.user_id)
    if user is None:  # deleted after the lookup of the session
        raise ApiError(ErrorCode.UNAUTHENTICATED, "Sign in to continue")
    return me(user)


@router.patch(
    "/me",
    response_model=Me,
    responses=problem_responses(
        ErrorCode.UNAUTHENTICATED,
        ErrorCode.CSRF_FAILED,
        ErrorCode.NICK_TAKEN,
        ErrorCode.NICK_CHANGE_TOO_SOON,
        ErrorCode.VALIDATION_ERROR,
        ErrorCode.RATE_LIMITED,
    ),
    dependencies=[Depends(throttle)],
    openapi_extra=PHASE_2,
)
async def update_me(body: MeUpdate, signed_in: SignedIn, session: Session) -> Me:
    """Change the nick or the display name (FR-AUTH-02). NICK_CHANGE_TOO_SOON: `params.available_at`
    is when it may change again."""
    now = datetime.now(UTC)
    # Locked: two concurrent changes of the nick would both pass the check of 30 days.
    user = await _locked(session, signed_in)
    if "display_name" in body.model_fields_set:
        user.display_name = body.display_name
    if body.nick is not None:
        await change_nick(session, user, body.nick, now)
    await session.commit()
    return me(user, now)


@router.delete(
    "/me",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Me,
    responses=problem_responses(
        ErrorCode.UNAUTHENTICATED, ErrorCode.CSRF_FAILED, ErrorCode.RATE_LIMITED
    ),
    dependencies=[Depends(throttle)],
    openapi_extra=PHASE_2,
)
async def delete_me(signed_in: SignedIn, session: Session) -> Me:
    """Request deletion of the account in 7 days (FR-USR-05): `delete_at` is set, the profile is
    hidden at once, sessions stay so that POST /me/restore can cancel it. Repeating keeps the
    date. At `delete_at` the sessions end, and the account is deleted with its submissions,
    drafts, logins and consents."""
    now = datetime.now(UTC)
    user = await _locked(session, signed_in)
    ask_deletion(user, now)
    await session.commit()
    return me(user, now)


@router.post(
    "/me/restore",
    response_model=Me,
    responses=problem_responses(
        ErrorCode.UNAUTHENTICATED, ErrorCode.CSRF_FAILED, ErrorCode.RATE_LIMITED
    ),
    dependencies=[Depends(throttle)],
    openapi_extra=PHASE_2,
)
async def restore_me(signed_in: SignedIn, session: Session) -> Me:
    """Cancel a requested deletion; without one nothing changes."""
    user = await _locked(session, signed_in)
    user.delete_at = None
    await session.commit()
    return me(user)


@router.get(
    "/me/export",
    response_model=AccountExport,
    responses={
        200: {
            "description": "The data as an attachment",
            "headers": {"Content-Disposition": {"schema": {"type": "string"}}},
        },
        **problem_responses(ErrorCode.UNAUTHENTICATED, ErrorCode.RATE_LIMITED),
    },
    dependencies=[Depends(throttle)],
    openapi_extra=PHASE_2,
)
async def export_me(signed_in: SignedIn, session: Session) -> Response:
    """Own data with the code of every kept submission (FR-USR-05), as the file
    `apparatica-<nick>.json`."""
    user = await session.get(User, signed_in.user_id)
    if user is None:
        raise ApiError(ErrorCode.UNAUTHENTICATED, "Sign in to continue")
    data = await export_account(session, user, datetime.now(UTC))
    return Response(
        data.model_dump_json(indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="apparatica-{user.nick}.json"',
            "Cache-Control": PRIVATE,
        },
    )


@router.get(
    "/me/drafts/{slug}",
    response_model=Draft,
    responses=problem_responses(
        ErrorCode.UNAUTHENTICATED,
        ErrorCode.NOT_FOUND,
        ErrorCode.VALIDATION_ERROR,
    ),
    openapi_extra=PHASE_2,
)
async def get_draft(response: Response, signed_in: SignedIn, session: Session, slug: Slug) -> Draft:
    """The saved draft of a problem; NOT_FOUND: none (FR-EDT-02)."""
    draft = await drafts.get_draft(session, signed_in.user_id, slug)
    if draft is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"No draft of {slug!r}")
    response.headers["Cache-Control"] = PRIVATE
    return draft


@router.put(
    "/me/drafts/{slug}",
    response_model=Draft,
    responses=problem_responses(
        ErrorCode.UNAUTHENTICATED,
        ErrorCode.CSRF_FAILED,
        ErrorCode.NOT_FOUND,
        ErrorCode.CODE_TOO_LARGE,
        ErrorCode.VALIDATION_ERROR,
        ErrorCode.RATE_LIMITED,
    ),
    dependencies=[Depends(draft_throttle)],
    openapi_extra=PHASE_2,
)
async def save_draft(
    request: Request,
    response: Response,
    signed_in: SignedIn,
    session: Session,
    slug: Slug,
    body: DraftSave,
) -> Draft:
    """Save the draft of a published problem; the last save wins. NOT_FOUND: no such problem.
    RATE_LIMITED: the autosave has its own window, apart from the other requests."""
    draft = await drafts.save_draft(
        session,
        signed_in.user_id,
        slug,
        body,
        limits=request.app.state.platform.limits.solution,
        now=datetime.now(UTC),
    )
    response.headers["Cache-Control"] = PRIVATE
    return draft


@router.get(
    "/users/{nick}",
    response_model=Profile,
    responses=problem_responses(ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR),
    openapi_extra=PHASE_2,
)
async def get_profile(
    request: Request, session: Session, nick: Annotated[Nick, Path()]
) -> Response:
    """A public profile (FR-USR-04). NOT_FOUND also for a hidden account or one being deleted."""
    levels = [level.key for level in request.app.state.platform.difficulties]
    profile = await profiles.get_profile(session, nick, levels, datetime.now(UTC).date())
    if profile is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"No user {nick!r}")
    return cached_json(request, profile)


@router.get(
    "/users/{nick}/solutions",
    response_model=UserSolutionPage,
    responses=problem_responses(ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR),
    openapi_extra=PHASE_3,
)
async def list_user_solutions(
    request: Request,
    session: Session,
    nick: Annotated[Nick, Path()],
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Response:
    """Public solutions of a user, newest first, with their places in the leaderboards pages
    show now (FR-USR-04). NOT_FOUND as for the profile."""
    user = await profiles.find_user(session, nick)
    if user is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"No user {nick!r}")
    body = await user_solutions(session, user.id, page=page, per_page=per_page)
    return cached_json(request, body)
