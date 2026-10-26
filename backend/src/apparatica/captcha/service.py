"""When a guest check needs a captcha (FR-GST-05): always with the `captcha` feature flag, and once
a guest or an address has sent `captcha.per_guest` / `captcha.per_ip` checks in their windows
(`config/rate-limits.yaml`). The windows are moving windows in valkey-cache, like the other rate
limits: an unreachable cache asks for no captcha.
"""

import uuid
from typing import Literal

from apparatica.captcha.altcha import Altcha
from apparatica.core.errors import ApiError, ErrorCode
from apparatica.core.flags import FeatureFlags
from apparatica.core.platform import CaptchaRules, Window
from apparatica.core.ratelimit import RateLimiter

CHALLENGE_URL = "/api/v1/captcha/challenge"
Reason = Literal["always", "frequent", "invalid"]


def captcha_required(reason: Reason) -> ApiError:
    """CAPTCHA_REQUIRED: `params.reason` says why — `always` (the flag), `frequent` (the guest or
    the address sends checks too often), `invalid` (the solution is wrong, expired or used)."""
    return ApiError(
        ErrorCode.CAPTCHA_REQUIRED,
        "Solve the challenge and repeat the request with `captcha`",
        params={"challenge_url": CHALLENGE_URL, "reason": reason},
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
        if await self._flags.enabled("captcha"):
            reason: Reason = "always"
        else:
            for window, scope, key in self._windows(guest_id, address):
                if (await self._limiter.state(window, scope, key)).remaining == 0:
                    reason = "frequent"
                    break
            else:
                return
        if solution is None:
            raise captcha_required(reason)
        signature = self.altcha.verify(solution)
        if signature is None:
            raise captcha_required("invalid")
        once = Window(limit=1, window_s=self._rules.expires_s)
        if await self._limiter.hit(once, "captcha:used", signature) is not None:
            raise captcha_required("invalid")

    async def count(self, guest_id: uuid.UUID, address: str | None) -> None:
        """Count a check that was stored."""
        for window, scope, key in self._windows(guest_id, address):
            await self._limiter.hit(window, scope, key)
