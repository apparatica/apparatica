"""Rate limits of the mutating endpoints and of logins (NFR-SEC-06): per client address, per guest
and per signed-in user."""

from fastapi import Request

from apparatica.auth.guests import Guest
from apparatica.auth.sessions import CurrentSession
from apparatica.core.errors import ApiError
from apparatica.core.ratelimit import rate_limited


async def throttle(request: Request, guest: Guest, session: CurrentSession) -> None:
    """FastAPI dependency of a mutating route: RATE_LIMITED (`quota: requests`) when the address or
    the author (the user, else the guest) sends too many requests."""
    state = request.app.state
    rules = state.platform.rate_limits
    author: tuple[str, str | None]
    if session is not None:
        author = ("requests:user", str(session.user_id))
    else:
        author = ("requests:guest", str(guest) if guest else None)
    keys = (
        (rules.requests_per_ip, "requests:ip", state.client_addresses.hash(request)),
        (rules.requests_per_author, *author),
    )
    for window, scope, key in keys:
        if key is None:
            continue
        retry = await state.rate_limiter.hit(window, scope, key)
        if retry is not None:
            raise rate_limited(
                "requests",
                f"At most {window.limit} requests per {window.window_s} s",
                limit=window.limit,
                window_s=window.window_s,
                retry_after_s=retry,
            )


async def login_throttle(request: Request) -> None:
    """FastAPI dependency of a route that starts a login or uses a login link: RATE_LIMITED
    (`quota: logins`) when the address does it too often."""
    error = await login_limit(request)
    if error is not None:
        raise error


async def login_limit(request: Request) -> ApiError | None:
    """Count a login of the address; the RATE_LIMITED error when its window is full."""
    state = request.app.state
    window = state.platform.rate_limits.logins_per_ip
    address = state.client_addresses.hash(request)
    if address is None:
        return None
    retry = await state.rate_limiter.hit(window, "logins:ip", address)
    if retry is None:
        return None
    return rate_limited(
        "logins",
        f"At most {window.limit} logins per {window.window_s} s from one address",
        limit=window.limit,
        window_s=window.window_s,
        retry_after_s=retry,
    )
