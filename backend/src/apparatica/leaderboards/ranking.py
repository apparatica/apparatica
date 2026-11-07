"""The leaderboards of problems (FR-LB-01/02/04, ADR-0006): the ingestor ranks an accepted Submit
in the transaction that stores its verdict, so the place is known before `finalized` (FR-LB-06).

- A leaderboard is the entries of one key: problem, epoch, toolchain profile, formula version
  (`BoardKey`). A Submit enters the leaderboard of its own key; pages and places show the key of
  the current version of the problem on the default profile.
- An entry is the best Submit of a signed-in user: lower `sort_values`, then the earlier Submit.
  A Submit that does not beat the entry of its author leaves it as it is.
- After a change the groups and places of the leaderboard are counted again by one statement: the
  earliest entry with an AST hash leads its group, the later ones follow it without a place
  (FR-LB-04); leaders take `RANK()` by `sort_values`, so equal arrays share a place (1, 2, 2, 4).
- Changes of one leaderboard are serialized by a transaction advisory lock: each count sees the
  entries the previous one committed. A transaction takes the locks of several leaderboards in
  the order of their keys.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import astuple, dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, Select, func, literal, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from apparatica.core.ids import uuid7
from apparatica.leaderboards.models import LeaderboardEntry
from apparatica.problems.models import Problem, ProblemVersion
from apparatica.submissions.models import Submission, ToolchainProfile
from apparatica.submissions.schemas import LeaderboardPlacement
from judge.core.leaderboard import ast_hash, leaderboard_metrics, sort_values
from judge.core.package import Leaderboard
from judge.core.package import Problem as Package
from judge.core.stage import StageResult


@dataclass(frozen=True, order=True)
class BoardKey:
    problem_id: uuid.UUID
    leaderboard_epoch: int
    toolchain_profile_id: str
    formula_version: int

    def where(self) -> list[ColumnElement[bool]]:
        return [
            LeaderboardEntry.problem_id == self.problem_id,
            LeaderboardEntry.leaderboard_epoch == self.leaderboard_epoch,
            LeaderboardEntry.toolchain_profile_id == self.toolchain_profile_id,
            LeaderboardEntry.formula_version == self.formula_version,
        ]


async def rank_submit(
    session: AsyncSession, submission: Submission, results: Sequence[StageResult], now: datetime
) -> bool:
    """Enter an accepted Submit of a signed-in user into the leaderboard of its problem: whether
    it ranks (FR-LB-02, FR-JDG-13)."""
    assert submission.user_id is not None
    version = await session.get(ProblemVersion, submission.problem_version_id)
    assert version is not None  # a foreign key
    package = Package.model_validate(version.manifest)
    metrics = leaderboard_metrics(package, results)
    if metrics is None or package.leaderboard is None:
        return False
    key = BoardKey(
        version.problem_id,
        version.leaderboard_epoch,
        submission.toolchain_profile_id,
        package.leaderboard.formula_version,
    )
    await _lock(session, [key])
    statement = insert(LeaderboardEntry).values(
        id=uuid7(),
        problem_id=key.problem_id,
        leaderboard_epoch=key.leaderboard_epoch,
        toolchain_profile_id=key.toolchain_profile_id,
        formula_version=key.formula_version,
        user_id=submission.user_id,
        submission_id=submission.id,
        # Through the shortest decimal of the float: 0.172, not 0.17199999999999998.
        sort_values=[Decimal(repr(value)) for value in sort_values(package.leaderboard, metrics)],
        ast_hash=ast_hash(results),
        submitted_at=submission.created_at,
        updated_at=now,
    )
    new = statement.excluded
    await session.execute(
        statement.on_conflict_do_update(
            constraint="uq_leaderboard_entries_user",
            set_={
                "submission_id": new.submission_id,
                "sort_values": new.sort_values,
                "ast_hash": new.ast_hash,
                "submitted_at": new.submitted_at,
                "updated_at": new.updated_at,
            },
            where=tuple_(new.sort_values, new.submitted_at)
            < tuple_(LeaderboardEntry.sort_values, LeaderboardEntry.submitted_at),
        )
    )
    await _recount(session, key, now)
    return True


async def boards_of(session: AsyncSession, user_id: uuid.UUID) -> list[BoardKey]:
    """The leaderboards with an entry of the user, to count again after it is deleted."""
    rows = await session.execute(
        select(
            LeaderboardEntry.problem_id,
            LeaderboardEntry.leaderboard_epoch,
            LeaderboardEntry.toolchain_profile_id,
            LeaderboardEntry.formula_version,
        )
        .where(LeaderboardEntry.user_id == user_id)
        .distinct()
    )
    return sorted(BoardKey(*row) for row in rows)


async def recount(session: AsyncSession, keys: Iterable[BoardKey], now: datetime) -> None:
    """Count the groups and places of the leaderboards again, e.g. after entries were deleted."""
    ordered = sorted(set(keys))
    await _lock(session, ordered)
    for key in ordered:
        await _recount(session, key, now)


async def _lock(session: AsyncSession, keys: Sequence[BoardKey]) -> None:
    for key in keys:
        name = "leaderboard:" + ":".join(str(part) for part in astuple(key))
        await session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(literal(name), 0)))
        )


# Leaders of groups: the earliest entry of each AST hash (an entry without one leads alone).
# Places: RANK() of the leaders by sort_values. Only rows that change are written.
_RECOUNT = text("""
WITH board AS (
    SELECT id,
           sort_values,
           first_value(id) OVER (
               PARTITION BY coalesce(ast_hash, id::text) ORDER BY submitted_at, id
           ) AS leader
    FROM leaderboard_entries
    WHERE problem_id = :problem_id
      AND leaderboard_epoch = :leaderboard_epoch
      AND toolchain_profile_id = :toolchain_profile_id
      AND formula_version = :formula_version
), places AS (
    SELECT id, rank() OVER (ORDER BY sort_values) AS rank FROM board WHERE leader = id
)
UPDATE leaderboard_entries AS entry
SET group_leader_entry_id = nullif(board.leader, board.id),
    rank = places.rank,
    updated_at = :now
FROM board LEFT JOIN places ON places.id = board.id
WHERE entry.id = board.id
  AND (entry.group_leader_entry_id IS DISTINCT FROM nullif(board.leader, board.id)
       OR entry.rank IS DISTINCT FROM places.rank)
""")


async def _recount(session: AsyncSession, key: BoardKey, now: datetime) -> None:
    await session.execute(
        _RECOUNT,
        {
            "problem_id": key.problem_id,
            "leaderboard_epoch": key.leaderboard_epoch,
            "toolchain_profile_id": key.toolchain_profile_id,
            "formula_version": key.formula_version,
            "now": now,
        },
    )


async def placement_of(
    session: AsyncSession, submission: Submission
) -> LeaderboardPlacement | None:
    """The place of the author of a public Submit in the leaderboard it entered (FR-RUN-05): the
    entry of the author is this Submit or a better one. None if the Submit is not public, its
    problem has no leaderboard, or the leaderboard is no longer the current one (another epoch,
    formula or default profile)."""
    if not submission.is_public or submission.user_id is None:
        return None
    key = await _current_key(session, submission)
    if key is None:
        return None
    leader = aliased(LeaderboardEntry)
    place = func.coalesce(LeaderboardEntry.rank, leader.rank)  # a follower has its leader's

    def board[*Ts](statement: Select[*Ts]) -> Select[*Ts]:
        return (
            statement.select_from(LeaderboardEntry)
            .outerjoin(leader, leader.id == LeaderboardEntry.group_leader_entry_id)
            .where(*key.where())
        )

    found = (
        await session.execute(
            board(select(LeaderboardEntry.submission_id, leader.submission_id, place)).where(
                LeaderboardEntry.user_id == submission.user_id
            )
        )
    ).one_or_none()
    if found is None or found[2] is None:
        return None
    entry_submission, leader_submission, rank = found
    total, lower = (
        await session.execute(board(select(func.count(), func.count().filter(place > rank))))
    ).one()
    return LeaderboardPlacement(
        rank=rank,
        total=total,
        better_than=round(lower / max(1, total - 1), 4),
        is_best=entry_submission == submission.id,
        duplicate_of=leader_submission,
    )


async def _current_key(session: AsyncSession, submission: Submission) -> BoardKey | None:
    """The key of the leaderboard the Submit entered, if pages show it now."""
    version = await session.get(ProblemVersion, submission.problem_version_id)
    assert version is not None  # a foreign key
    problem = await session.get(Problem, version.problem_id)
    assert problem is not None
    current = (
        version
        if problem.current_version_id in (None, version.id)
        else await session.get(ProblemVersion, problem.current_version_id)
    )
    assert current is not None
    key = await current_key(session, current)
    formula = _formula_version(version.manifest)
    if key is None or formula is None:
        return None
    entered = BoardKey(
        version.problem_id, version.leaderboard_epoch, submission.toolchain_profile_id, formula
    )
    return key if entered == key else None


async def current_key(session: AsyncSession, current: ProblemVersion) -> BoardKey | None:
    """The leaderboard that pages show for the current version of a problem: its epoch and
    formula on the default toolchain profile of its language. None: the version has no
    leaderboard, or the language has no default profile."""
    formula = _formula_version(current.manifest)
    if formula is None:
        return None
    default = await default_profile(session, current.language)
    if default is None:
        return None
    return BoardKey(current.problem_id, current.leaderboard_epoch, default, formula)


async def default_profile(session: AsyncSession, language: str) -> str | None:
    """The toolchain profile that checks new submissions of the language."""
    return await session.scalar(
        select(ToolchainProfile.id).where(
            ToolchainProfile.language == language, ToolchainProfile.is_default
        )
    )


def _formula_version(manifest: dict[str, object]) -> int | None:
    leaderboard = manifest.get("leaderboard")
    return None if leaderboard is None else Leaderboard.model_validate(leaderboard).formula_version
