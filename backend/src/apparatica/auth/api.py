"""Login and logout (specs/05 §3, phase 2).

A login sets the session cookie `ap_session` (ADR-0010). The first login creates the account with
the current versions of the legal documents as accepted: the login page says that continuing
accepts them (FR-AUTH-06). Starts of logins and uses of login links are limited per address
(NFR-SEC-06).
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Query, Request, status
from fastapi.responses import RedirectResponse, Response

from apparatica.auth import oauth
from apparatica.auth.accounts import me
from apparatica.auth.email_login import EmailLogins, normalize
from apparatica.auth.oauth import LoginError, OAuthLogins
from apparatica.auth.schemas import (
    EmailLogin,
    EmailLoginRequest,
    EmailLoginVerify,
    NextPath,
    OAuthProvider,
)
from apparatica.auth.sessions import COOKIE, Sessions, SignedIn
from apparatica.auth.throttle import email_throttle, login_limit, login_throttle, throttle
from apparatica.core.errors import ApiError, ErrorCode, problem_responses

router = APIRouter(tags=["auth"])

PHASE_2 = {"x-phase": 2}
LOGIN_FAILED = "/login?error={reason}"  # a page of the site; reasons in docs/api.md
Provider = Annotated[OAuthProvider, Path(description="Enabled providers are in GET /config")]


async def _email_logins(request: Request) -> EmailLogins:
    """NOT_FOUND unless email login is configured (SMTP) and its flag `auth_email` is on."""
    state = request.app.state
    email_logins: EmailLogins | None = state.email_logins
    if email_logins is None or not await state.flags.enabled("auth_email"):
        raise ApiError(ErrorCode.NOT_FOUND, "Email login is not enabled")
    return email_logins


async def _oauth_logins(request: Request, provider: str) -> OAuthLogins:
    """NOT_FOUND unless the OAuth app of the provider is configured and its flag is on."""
    state = request.app.state
    logins: OAuthLogins | None = state.oauth_logins.get(provider)
    if logins is None or not await state.flags.enabled(f"auth_{provider}"):
        raise ApiError(ErrorCode.NOT_FOUND, f"Login with {provider} is not enabled")
    return logins


async def _replace_session(request: Request, response: Response, token: str) -> None:
    """Give the browser the session of a login, ending the one it had."""
    sessions: Sessions = request.app.state.sessions
    previous = request.cookies.get(COOKIE)
    if previous is not None:
        await sessions.end(previous)
    sessions.set_cookie(response, token)


@router.get(
    "/auth/{provider}/login",
    status_code=status.HTTP_302_FOUND,
    response_class=RedirectResponse,
    responses={
        302: {
            "description": "Redirect to the authorization page of the provider; to "
            "/login?error=rate_limited when the address starts logins too often",
            "headers": {"Location": {"schema": {"type": "string", "format": "uri"}}},
        },
        **problem_responses(ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR),
    },
    openapi_extra=PHASE_2,
)
async def oauth_login(
    provider: Provider, request: Request, next: Annotated[NextPath | None, Query()] = None
) -> RedirectResponse:
    """Start a login with an OAuth provider: a page the browser navigates to, not a fetch, so
    the rate limit is a redirect to the login page too. NOT_FOUND: the provider is disabled."""
    logins = await _oauth_logins(request, provider)
    if await login_limit(request) is not None:
        return RedirectResponse(LOGIN_FAILED.format(reason="rate_limited"), status.HTTP_302_FOUND)
    url, pending = logins.start(next)
    response = RedirectResponse(url, status.HTTP_302_FOUND)
    logins.set_cookie(response, pending)
    return response


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
        **problem_responses(ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR),
    },
    openapi_extra=PHASE_2,
)
async def oauth_callback(
    provider: Provider,
    request: Request,
    code: Annotated[str | None, Query(max_length=2048)] = None,
    state: Annotated[str | None, Query(max_length=2048)] = None,
    error: Annotated[str | None, Query(max_length=256, description="Set by the provider")] = None,
) -> RedirectResponse:
    """Where the provider returns the browser. A failure is a redirect to the login page, not an
    error document: the browser shows the page. The first login creates the account; the login
    replaces the session of this browser."""
    logins = await _oauth_logins(request, provider)
    response: RedirectResponse
    try:
        login = await logins.finish(
            code=code,
            state=state,
            error=error,
            cookie=request.cookies.get(oauth.COOKIE),
            user_agent=request.headers.get("user-agent"),
        )
    except LoginError as failed:
        response = RedirectResponse(
            LOGIN_FAILED.format(reason=failed.reason), status.HTTP_302_FOUND
        )
    else:
        response = RedirectResponse(login.next or "/", status.HTTP_302_FOUND)
        await _replace_session(request, response, login.session_token)
    logins.clear_cookie(response)  # a login is finished once, whatever the answer
    return response


@router.post(
    "/auth/email/request",
    status_code=status.HTTP_202_ACCEPTED,
    response_class=Response,
    responses={
        202: {"description": "A link is sent if the address can sign in; the same either way"},
        **problem_responses(
            ErrorCode.NOT_FOUND,
            ErrorCode.VALIDATION_ERROR,
            ErrorCode.CSRF_FAILED,
            ErrorCode.CAPTCHA_REQUIRED,
            ErrorCode.RATE_LIMITED,
        ),
    },
    dependencies=[Depends(throttle), Depends(login_throttle)],
    openapi_extra=PHASE_2,
)
async def request_login_link(
    body: EmailLoginRequest, request: Request, background: BackgroundTasks
) -> None:
    """Send a one-time login link valid for 15 minutes (FR-AUTH-05). The answer does not tell
    whether an account exists. NOT_FOUND: email login is disabled; RATE_LIMITED: per email address
    and per IP; CAPTCHA_REQUIRED: with the `captcha` flag."""
    email_logins = await _email_logins(request)
    await request.app.state.captcha.check_login(body.captcha)
    await email_throttle(request, normalize(body.email))
    letter = await email_logins.request(body.email, body.next)
    # After the answer: its time does not depend on the mail server, failures are only logged.
    background.add_task(email_logins.send, letter)


@router.post(
    "/auth/email/verify",
    response_model=EmailLogin,
    responses=problem_responses(
        ErrorCode.NOT_FOUND,
        ErrorCode.LOGIN_LINK_INVALID,
        ErrorCode.VALIDATION_ERROR,
        ErrorCode.CSRF_FAILED,
        ErrorCode.RATE_LIMITED,
    ),
    dependencies=[Depends(throttle), Depends(login_throttle)],
    openapi_extra=PHASE_2,
)
async def verify_login_link(
    body: EmailLoginVerify, request: Request, response: Response
) -> EmailLogin:
    """Sign in with the token of a link. The link opens a page of the site that posts the token,
    so a link preview that fetches it does not spend it. The first login creates the account.
    LOGIN_LINK_INVALID: unknown, used or expired; NOT_FOUND: email login is disabled."""
    email_logins = await _email_logins(request)
    login = await email_logins.verify(body.token, request.headers.get("user-agent"))
    if login is None:
        raise ApiError(ErrorCode.LOGIN_LINK_INVALID, "The link is unknown, used or expired")
    await _replace_session(request, response, login.session_token)
    return EmailLogin(user=me(login.user), created=login.created, next=login.next)


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={
        204: {"description": "The session is ended and its cookie cleared"},
        **problem_responses(ErrorCode.CSRF_FAILED, ErrorCode.RATE_LIMITED),
    },
    dependencies=[Depends(throttle)],
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
        **problem_responses(
            ErrorCode.UNAUTHENTICATED, ErrorCode.CSRF_FAILED, ErrorCode.RATE_LIMITED
        ),
    },
    dependencies=[Depends(throttle)],
    openapi_extra=PHASE_2,
)
async def logout_all(session: SignedIn, request: Request, response: Response) -> None:
    """End every session of the user, this one included (FR-AUTH-04)."""
    sessions: Sessions = request.app.state.sessions
    await sessions.end_all(session.user_id)
    sessions.clear_cookie(response)
