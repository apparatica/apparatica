"""Login and logout (specs/05 §3, phase 2): the contract, stubs until T2.1a-T2.3.

A login sets the session cookie `ap_session` and the CSRF cookie `ap_csrf` (ADR-0010). The first
login creates the account with the current versions of the legal documents as accepted: the login
page says that continuing accepts them (FR-AUTH-06).
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request, status
from fastapi.responses import RedirectResponse, Response

from apparatica.auth.schemas import (
    EmailLogin,
    EmailLoginRequest,
    EmailLoginVerify,
    NextPath,
    OAuthProvider,
)
from apparatica.auth.sessions import COOKIE, Sessions, SignedIn
from apparatica.core.errors import ApiError, ErrorCode, problem_responses

router = APIRouter(tags=["auth"])

PHASE_2 = {"x-phase": 2}
Provider = Annotated[OAuthProvider, Path(description="Enabled providers are in GET /config")]


def _stub(task: str) -> ApiError:
    return ApiError(
        ErrorCode.NOT_IMPLEMENTED, f"Declared by the phase 2 contract; arrives in {task}"
    )


@router.get(
    "/auth/{provider}/login",
    status_code=status.HTTP_302_FOUND,
    response_class=RedirectResponse,
    responses={
        302: {
            "description": "Redirect to the authorization page of the provider",
            "headers": {"Location": {"schema": {"type": "string", "format": "uri"}}},
        },
        **problem_responses(
            ErrorCode.NOT_IMPLEMENTED, ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR
        ),
    },
    openapi_extra=PHASE_2,
)
async def oauth_login(
    provider: Provider, next: Annotated[NextPath | None, Query()] = None
) -> RedirectResponse:
    """Start a login with an OAuth provider: a page the browser navigates to, not a fetch.
    NOT_FOUND: the provider is disabled."""
    raise _stub("T2.3")


@router.get(
    "/auth/{provider}/callback",
    status_code=status.HTTP_302_FOUND,
    response_class=RedirectResponse,
    responses={
        302: {
            "description": "Signed in: to `next` of the login. Failed: to /login?error=<reason>, "
            "reasons in docs/api.md",
            "headers": {"Location": {"schema": {"type": "string"}}},
        },
        **problem_responses(
            ErrorCode.NOT_IMPLEMENTED, ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR
        ),
    },
    openapi_extra=PHASE_2,
)
async def oauth_callback(
    provider: Provider,
    code: Annotated[str | None, Query(max_length=2048)] = None,
    state: Annotated[str | None, Query(max_length=2048)] = None,
    error: Annotated[str | None, Query(max_length=256, description="Set by the provider")] = None,
) -> RedirectResponse:
    """Where the provider returns the browser. A failure is a redirect to the login page, not an
    error document: the browser shows the page."""
    raise _stub("T2.3")


@router.post(
    "/auth/email/request",
    status_code=status.HTTP_202_ACCEPTED,
    response_class=Response,
    responses={
        202: {"description": "A link is sent if the address can sign in; the same either way"},
        **problem_responses(
            ErrorCode.NOT_IMPLEMENTED,
            ErrorCode.VALIDATION_ERROR,
            ErrorCode.CSRF_FAILED,
            ErrorCode.CAPTCHA_REQUIRED,
            ErrorCode.RATE_LIMITED,
        ),
    },
    openapi_extra=PHASE_2,
)
async def request_login_link(body: EmailLoginRequest) -> None:
    """Send a one-time login link valid for 15 minutes (FR-AUTH-05). The answer does not tell
    whether an account exists. RATE_LIMITED: per address and per IP; CAPTCHA_REQUIRED: as for
    submissions."""
    raise _stub("T2.2")


@router.post(
    "/auth/email/verify",
    response_model=EmailLogin,
    responses=problem_responses(
        ErrorCode.NOT_IMPLEMENTED,
        ErrorCode.LOGIN_LINK_INVALID,
        ErrorCode.VALIDATION_ERROR,
        ErrorCode.CSRF_FAILED,
        ErrorCode.RATE_LIMITED,
    ),
    openapi_extra=PHASE_2,
)
async def verify_login_link(body: EmailLoginVerify) -> EmailLogin:
    """Sign in with the token of a link. The link opens a page of the site that posts the token,
    so a link preview that fetches it does not spend it. LOGIN_LINK_INVALID: unknown, used or
    expired."""
    raise _stub("T2.2")


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={
        204: {"description": "The session is ended and its cookies cleared"},
        **problem_responses(ErrorCode.CSRF_FAILED),
    },
    openapi_extra=PHASE_2,
)
async def logout(request: Request, response: Response) -> None:
    """End the session of the request; without one there is nothing to end."""
    sessions: Sessions = request.app.state.sessions
    token = request.cookies.get(COOKIE)
    if token is not None:
        await sessions.end(token)
    sessions.clear_cookie(response)


@router.post(
    "/auth/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={
        204: {"description": "Every session of the user is ended"},
        **problem_responses(ErrorCode.UNAUTHENTICATED, ErrorCode.CSRF_FAILED),
    },
    openapi_extra=PHASE_2,
)
async def logout_all(session: SignedIn, request: Request, response: Response) -> None:
    """End every session of the user, this one included (FR-AUTH-04)."""
    sessions: Sessions = request.app.state.sessions
    await sessions.end_all(session.user_id)
    sessions.clear_cookie(response)
