"""When a guest check needs a captcha (FR-GST-05): always with the `captcha` feature flag, and once
a guest or an address has sent `captcha.per_guest` / `captcha.per_ip` checks in their windows
(`config/rate-limits.yaml`). The windows are moving windows in valkey-cache, like the other rate
limits: an unreachable cache asks for no captcha.
"""

import math
import time
import uuid
from typing import Literal

from apparatica.captcha.altcha import Altcha
from apparatica.core.errors import ApiError, ErrorCode
from apparatica.core.flags import FeatureFlags
from apparatica.core.platform import CaptchaRules, Window
from apparatica.core.ratelimit import RateLimiter

CHALLENGE_URL = "/api/v1/captcha/challenge"
Reason = Literal["always", "frequent", "invalid"]


def captcha_required(reason: Reason, retry_after_s: float | None = None) -> ApiError:
    """CAPTCHA_REQUIRED: `params.reason` says why — `always` (the flag), `frequent` (the guest or
    the address sends checks too often), `invalid` (the solution is wrong, expired or used).
    `params.retry_after_s`: when checks are frequent, the wait after which none is needed."""
    params: dict[str, object] = {"challenge_url": CHALLENGE_URL, "reason": reason}
    if retry_after_s is not None:
        params["retry_after_s"] = max(1, math.ceil(retry_after_s))
    return ApiError(
        ErrorCode.CAPTCHA_REQUIRED,
        "Solve the challenge and repeat the request with `captcha`",
        params=params,
    )


class Captcha:
    def __init__(
        self, altcha: Altcha, limiter: RateLimiter, rules: CaptchaRules, flags: FeatureFlags
    ) -> None:
        self.altcha = altcha
        self._limiter, self._rules, self._flags = limiter, rules, flags

    def _windows(self, guest_id: uuid.UUID, address: str | None) -> list[tuple[Window, str, str]]:
        rules = self._rules
        windows = [(rules.per_guest, "captcha:guest", str(guest_id))]
        if address is not None:
            windows.append((rules.per_ip, "captcha:ip", address))
        return windows

    async def check(self, guest_id: uuid.UUID, address: str | None, solution: str | None) -> None:
        """Raise CAPTCHA_REQUIRED unless no captcha is needed or `solution` is a valid one; a
        needless solution is not looked at."""
        retry: float | None = None
        if await self._flags.enabled("captcha"):
            reason: Reason = "always"
        else:
            # Each full window must free a slot: the wait is the longest of them.
            resets = [
                state.reset_at
                for window, scope, key in self._windows(guest_id, address)
                if (state := await self._limiter.state(window, scope, key)).remaining == 0
            ]
            if not resets:
                return
            reason = "frequent"
            known = [reset.timestamp() for reset in resets if reset is not None]
            retry = max(known) - time.time() if known else None
        if solution is None:
            raise captcha_required(reason, retry)
        signature = self.altcha.verify(solution)
        if signature is None:
            raise captcha_required("invalid", retry)
        once = Window(limit=1, window_s=self._rules.expires_s)
        if await self._limiter.hit(once, "captcha:used", signature) is not None:
            raise captcha_required("invalid", retry)

    async def count(self, guest_id: uuid.UUID, address: str | None) -> None:
        """Count a check that was stored."""
        for window, scope, key in self._windows(guest_id, address):
            await self._limiter.hit(window, scope, key)
