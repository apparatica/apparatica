"""Feature flags (specs/03 §7): the known flags and their defaults are code; deployments override
them, from T0.15 in the `feature_flags` table edited in SQLAdmin. Values are cached in process for
`feature_flags_ttl_s` seconds; the frontend gets them from `GET /api/v1/config`.
"""

import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

import structlog

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class Flag:
    key: str
    default: bool
    description: str


# Login providers add `auth_<provider>` flags with their phases (Ф2, Ф4).
FLAGS: dict[str, Flag] = {
    flag.key: flag
    for flag in (
        Flag("captcha", False, "ALTCHA before guest checks (Ф1)"),
        Flag("formal_stage", False, "Formal verification stage and its result tab (Ф5)"),
        Flag("industrial_mode", False, "Industrial practice mode (Ф7)"),
        Flag("reports", False, "Reports about problems and solutions (Ф5)"),
    )
}

Overrides = Callable[[], Awaitable[Mapping[str, bool]]]


async def no_overrides() -> Mapping[str, bool]:
    return {}


class FeatureFlags:
    def __init__(
        self,
        overrides: Overrides = no_overrides,
        *,
        ttl_s: float = 30,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._overrides = overrides
        self._ttl_s = ttl_s
        self._clock = clock
        self._values: dict[str, bool] | None = None
        self._loaded_at = 0.0

    async def values(self) -> dict[str, bool]:
        now = self._clock()
        if self._values is None or now - self._loaded_at >= self._ttl_s:
            self._values = await self._load(self._values)
            self._loaded_at = now
        return dict(self._values)

    async def enabled(self, key: str) -> bool:
        if key not in FLAGS:
            raise KeyError(f"unknown feature flag {key!r}")
        return (await self.values())[key]

    async def _load(self, previous: dict[str, bool] | None) -> dict[str, bool]:
        values = {key: flag.default for key, flag in FLAGS.items()}
        try:
            overrides = await self._overrides()
        except Exception:
            # The flags must not take the API down: keep what was known, or the defaults.
            log.exception("cannot load feature flag overrides")
            return previous or values
        for key, value in overrides.items():
            if key in FLAGS:
                values[key] = value
            else:
                log.warning("unknown feature flag override", flag=key)
        return values
