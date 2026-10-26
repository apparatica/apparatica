"""Quotas of checks (specs/07 §3, FR-GST-04).

The quotas users see are exact and counted from their submissions in Postgres: a check that ended
in `internal_error` gives its slot back, and nothing is forgotten when a cache is evicted or
restarted. The submissions of one author are created one at a time under a transaction advisory
lock, so two parallel requests cannot both take the last slot.

Recreated waveforms (FR-WAV-05) have no rows of their own: their quota is a moving window in
valkey-cache, as are the checks of one client address, which catch a guest who drops the cookie
(`apparatica.core.ratelimit`).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.core.errors import ApiError, ErrorCode
from apparatica.core.platform import Quota, RateLimits, Window
from apparatica.core.ratelimit import RateLimiter, rate_limited
from apparatica.problems.models import ProblemVersion
from apparatica.submissions.models import Submission
from apparatica.submissions.schemas import QuotaStatus, QuotaWindow
from judge.core.stage import SubmissionKind

HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
UNFINISHED = ("queued", "running")
NOT_COUNTED = "internal_error"  # a failure of the platform costs the author nothing
HEAVY = "heavy"  # the resource class of heavy problems (config/resource-classes.yaml)


@dataclass(frozen=True)
class Author:
    """Who sends a check, and from which address (a salted hash): a guest until phase 2."""

    guest_id: uuid.UUID
    address: str | None


def _window(times: Sequence[datetime], limit: int, period: timedelta) -> QuotaWindow:
    """`times` are the counted events of the last `period`, oldest first."""
    remaining = max(limit - len(times), 0)
    reset_at = times[len(times) - limit] + period if remaining == 0 and times else None
    return QuotaWindow(limit=limit, remaining=remaining, reset_at=reset_at)


class Quotas:
    def __init__(self, quota: Quota, limiter: RateLimiter, rate_limits: RateLimits) -> None:
        self._quota, self._limiter, self._rate_limits = quota, limiter, rate_limits

    async def admit(
        self,
        session: AsyncSession,
        author: Author,
        *,
        kind: SubmissionKind,
        problem_id: uuid.UUID,
        resource_class: str,
    ) -> None:
        """Raise unless the author may start one more check. The lock of the author is held
        until the transaction that stores the submission ends."""
        lock = func.hashtextextended(f"submissions:{author.guest_id}", 0)
        await session.execute(select(func.pg_advisory_xact_lock(lock)))
        now = await session.scalar(select(func.now()))
        assert now is not None
        quota = self._quota
        if resource_class == HEAVY:
            if quota.heavy_per_day == 0:
                raise ApiError(
                    ErrorCode.HEAVY_NOT_ALLOWED, "Heavy problems are for signed-in users"
                )
            heavy = _window(
                await self._counted(session, author.guest_id, now - DAY, heavy_only=True),
                quota.heavy_per_day,
                DAY,
            )
            if heavy.remaining == 0:
                raise self._spent("heavy", heavy, DAY, now, "heavy checks per day")
        checks = _window(
            await self._counted(session, author.guest_id, now - HOUR),
            quota.checks_per_hour,
            HOUR,
        )
        if checks.remaining == 0:
            raise self._spent("checks", checks, HOUR, now, "checks per hour")

        unfinished = (
            select(func.count())
            .select_from(Submission)
            .where(Submission.guest_id == author.guest_id, Submission.status.in_(UNFINISHED))
        )
        if kind == "run":  # a new Run preempts the unfinished Runs of the problem (FR-JDG-10)
            versions = select(ProblemVersion.id).where(ProblemVersion.problem_id == problem_id)
            unfinished = unfinished.where(
                not_(and_(Submission.kind == "run", Submission.problem_version_id.in_(versions)))
            )
        if (await session.scalar(unfinished) or 0) >= quota.concurrent:
            raise rate_limited(
                "concurrent",
                f"At most {quota.concurrent} checks may run at once",
                limit=quota.concurrent,
            )

        if author.address is not None:
            window = self._rate_limits.checks_per_ip
            retry = await self._limiter.hit(window, "checks:ip", author.address)
            if retry is not None:
                raise rate_limited(
                    "checks_per_ip",
                    f"At most {window.limit} checks per {window.window_s} s from one address",
                    limit=window.limit,
                    window_s=window.window_s,
                    retry_after_s=retry,
                )

    async def status(self, session: AsyncSession, guest_id: uuid.UUID | None) -> QuotaStatus:
        """What is left of the quotas of a guest; all of it for a new one."""
        quota = self._quota
        if guest_id is None:
            full = QuotaWindow(
                limit=quota.checks_per_hour, remaining=quota.checks_per_hour, reset_at=None
            )
            waves = QuotaWindow(
                limit=quota.waveforms_per_hour, remaining=quota.waveforms_per_hour, reset_at=None
            )
            return QuotaStatus(checks=full, waveforms=waves)
        now = await session.scalar(select(func.now()))
        assert now is not None
        checks = _window(
            await self._counted(session, guest_id, now - HOUR), quota.checks_per_hour, HOUR
        )
        return QuotaStatus(checks=checks, waveforms=await self._waveforms(guest_id))

    async def admit_waveform(self, guest_id: uuid.UUID) -> None:
        """Count one recreated waveform of the guest, or raise when the hour's quota is spent."""
        limit = self._quota.waveforms_per_hour
        retry = (
            await self._limiter.hit(Window(limit=limit, window_s=3600), "waveforms", str(guest_id))
            if limit
            else None
        )
        if limit == 0 or retry is not None:
            raise rate_limited(
                "waveforms",
                f"At most {limit} waveforms per hour",
                limit=limit,
                window_s=3600,
                retry_after_s=retry,
            )

    async def _waveforms(self, guest_id: uuid.UUID) -> QuotaWindow:
        limit = self._quota.waveforms_per_hour
        if limit == 0:
            return QuotaWindow(limit=0, remaining=0, reset_at=None)
        state = await self._limiter.state(
            Window(limit=limit, window_s=3600), "waveforms", str(guest_id)
        )
        return QuotaWindow(limit=limit, remaining=state.remaining, reset_at=state.reset_at)

    @staticmethod
    async def _counted(
        session: AsyncSession, guest_id: uuid.UUID, since: datetime, *, heavy_only: bool = False
    ) -> list[datetime]:
        query = (
            select(Submission.created_at)
            .where(
                Submission.guest_id == guest_id,
                Submission.created_at > since,
                Submission.status != NOT_COUNTED,
            )
            .order_by(Submission.created_at)
        )
        if heavy_only:
            query = query.where(Submission.queue_class == HEAVY)
        return list(await session.scalars(query))

    @staticmethod
    def _spent(
        quota: str, window: QuotaWindow, period: timedelta, now: datetime, what: str
    ) -> ApiError:
        retry = (window.reset_at - now).total_seconds() if window.reset_at is not None else None
        return rate_limited(
            quota,
            f"Guest limit is {window.limit} {what}",
            limit=window.limit,
            window_s=int(period.total_seconds()),
            retry_after_s=retry,
        )
