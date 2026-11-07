"""Moderation (FR-ADM-02 in part, FR-ADM-03): a moderator hides a public solution or a user and
shows them again; an administrator also gives roles. Every change goes to `moderation_log` with
its reason, in the transaction of the change.

- A hidden solution leaves the public solutions and the leaderboard of its problem; the entry of
  its author is built again from their Submits left (`ranking.rebuild`). A hidden user leaves
  public pages, the leaderboards of problems and the global one, and enters none with new
  Submits; the user still signs in and solves.
- Staff accounts are not hidden: an administrator takes the role away first. Nobody changes their
  own role.
- Locks follow the ingestor (`apparatica.leaderboards.ranking`): the rows of the users in the
  order of their ids, then the leaderboards, then the global leaderboard.
"""

import uuid
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.admin.models import ModerationLog, TargetType
from apparatica.auth.models import User
from apparatica.auth.schemas import Role
from apparatica.core.db import Database
from apparatica.core.platform import RatingFormula
from apparatica.leaderboards import rating
from apparatica.leaderboards.ranking import rebuild
from apparatica.submissions.models import Submission

STAFF: tuple[Role, ...] = ("moderator", "admin")

# Why a change is refused: the panel shows its own text for each.
Refusal = Literal["staff_target", "own_role", "not_admin", "hidden_staff"]


class ModerationRefusedError(Exception):
    def __init__(self, refusal: Refusal) -> None:
        super().__init__(refusal)
        self.refusal: Refusal = refusal


@dataclass(frozen=True)
class Staff:
    """A moderator or an administrator who acts in the panel."""

    user_id: uuid.UUID
    nick: str
    role: Role


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Moderation:
    database: Database
    rating: RatingFormula
    clock: Callable[[], datetime] = _now

    async def hide_users(
        self, actor: Staff, user_ids: Collection[uuid.UUID], *, hidden: bool, reason: str
    ) -> int:
        """Hide the users, or show them again; returns how many changed. ModerationRefusedError
        `staff_target`: one of them is a moderator or an administrator (nothing changes)."""
        now = self.clock()
        async with self.database.sessions.begin() as session:
            users = await _lock_users(session, user_ids)
            if hidden and any(user.role in STAFF for user in users):
                raise ModerationRefusedError("staff_target")
            changed = [user for user in users if user.is_hidden != hidden]
            for user in changed:
                user.is_hidden = hidden
                _log(session, actor, "hide" if hidden else "unhide", "user", user.id, reason)
            await self._recount(session, [user.id for user in changed], now)
        return len(changed)

    async def hide_submissions(
        self, actor: Staff, submission_ids: Collection[uuid.UUID], *, hidden: bool, reason: str
    ) -> int:
        """Hide public solutions, or show them again; returns how many changed. An id of another
        submission is skipped."""
        now = self.clock()
        async with self.database.sessions.begin() as session:
            authors = await session.scalars(
                select(Submission.user_id).where(
                    Submission.id.in_(submission_ids), Submission.is_public
                )
            )
            await _lock_users(session, {author for author in authors if author is not None})
            submissions = (
                await session.scalars(
                    select(Submission)
                    .where(Submission.id.in_(submission_ids), Submission.is_public)
                    .order_by(Submission.id)
                )
            ).all()
            changed = [found for found in submissions if found.is_hidden != hidden]
            for submission in changed:
                submission.is_hidden = hidden
                _log(
                    session,
                    actor,
                    "hide" if hidden else "unhide",
                    "submission",
                    submission.id,
                    reason,
                )
            authors_changed = {found.user_id for found in changed if found.user_id is not None}
            await self._recount(session, sorted(authors_changed), now)
        return len(changed)

    async def set_role(self, actor: Staff, user_id: uuid.UUID, role: Role, reason: str) -> bool:
        """Give the user the role; whether it changed. ModerationRefusedError: `not_admin` (only
        an administrator gives roles), `own_role`, `hidden_staff` (a hidden user gets no staff
        role)."""
        if actor.role != "admin":
            raise ModerationRefusedError("not_admin")
        if user_id == actor.user_id:
            raise ModerationRefusedError("own_role")
        async with self.database.sessions.begin() as session:
            return await change_role(session, actor.user_id, user_id, role, reason)

    async def _recount(
        self, session: AsyncSession, user_ids: Collection[uuid.UUID], now: datetime
    ) -> None:
        if not user_ids:
            return
        await session.flush()
        await rebuild(session, user_ids, now)
        await rating.recount(session, self.rating, now)


async def change_role(
    session: AsyncSession, actor_id: uuid.UUID | None, user_id: uuid.UUID, role: Role, reason: str
) -> bool:
    """Give the user the role and log it; whether it changed. `actor_id` None: by the
    `apparatica-admin` command line."""
    user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None or user.role == role:
        return False
    if user.is_hidden and role in STAFF:
        raise ModerationRefusedError("hidden_staff")
    session.add(
        ModerationLog(
            actor_id=actor_id,
            action="set_role",
            target_type="user",
            target_id=str(user.id),
            reason=reason,
            details={"from": user.role, "to": role},
        )
    )
    user.role = role
    return True


async def _lock_users(session: AsyncSession, user_ids: Collection[uuid.UUID]) -> list[User]:
    """The rows of the users, locked for update in the order of their ids (the ingestor's
    `rank_submit` waits for them)."""
    if not user_ids:
        return []
    found = await session.scalars(
        select(User)
        .where(User.id.in_(user_ids))
        .order_by(User.id)
        .with_for_update(key_share=True)  # FOR NO KEY UPDATE: foreign keys to users still go
    )
    return list(found.all())


def _log(
    session: AsyncSession,
    actor: Staff,
    action: Literal["hide", "unhide"],
    target_type: TargetType,
    target_id: uuid.UUID,
    reason: str,
) -> None:
    session.add(
        ModerationLog(
            actor_id=actor.user_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            reason=reason,
        )
    )
