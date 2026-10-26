"""Rate limits of the mutating endpoints (NFR-SEC-06): per client address and per guest."""

from fastapi import Request

from apparatica.auth.guests import Guest
from apparatica.core.ratelimit import rate_limited


async def throttle(request: Request, guest: Guest) -> None:
    """FastAPI dependency of a mutating route: RATE_LIMITED (`quota: requests`) when the address or
    the guest sends too many requests."""
    state = request.app.state
    rules = state.platform.rate_limits
    keys = (
        (rules.requests_per_ip, "requests:ip", state.client_addresses.hash(request)),
        (rules.requests_per_author, "requests:guest", str(guest) if guest else None),
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
