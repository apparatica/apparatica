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
- A Submit hidden by a moderator, and every Submit of a hidden user, ranks nowhere (FR-ADM-03):
  hiding and showing again rebuild the entries of the user from the Submits left (`rebuild`).
  The row of the user is the lock between them and the ingestor: a moderator holds it for
  update, `rank_submit` for share, and both take it before the leaderboards.
"""

import uuid
from collections.abc import Collection, Iterable, Sequence
from dataclasses import astuple, dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    ColumnElement,
    Integer,
    Select,
    Subquery,
    and_,
    cast,
    delete,
    func,
    literal,
    select,
    text,
    tuple_,
)
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from apparatica.auth.models import User
from apparatica.core.ids import uuid7
from apparatica.leaderboards.models import LeaderboardEntry
from apparatica.problems.models import Problem, ProblemVersion
from apparatica.submissions.models import StageResult as StageRow
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
    it ranks (FR-LB-02, FR-JDG-13). A hidden user ranks nowhere (FR-ADM-03)."""
    assert submission.user_id is not None
    hidden = await session.scalar(
        select(User.is_hidden).where(User.id == submission.user_id).with_for_update(read=True)
    )
    if hidden or submission.is_hidden:
        return False
    version = await session.get(ProblemVersion, submission.problem_version_id)
    assert version is not None  # a foreign key
    entry = _entry(submission, version, results)
    if entry is None:
        return False
    key, values = entry
    await lock(session, [key])
    statement = _insert(submission, key, values, ast_hash(results), now)
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


def _entry(
    submission: Submission, version: ProblemVersion, results: Sequence[StageResult]
) -> tuple[BoardKey, list[Decimal]] | None:
    """The leaderboard a Submit enters and its `sort_values`; None: it does not rank."""
    package = Package.model_validate(version.manifest)
    metrics = leaderboard_metrics(package, results)
    if metrics is None or package.leaderboard is None:
        return None
    key = BoardKey(
        version.problem_id,
        version.leaderboard_epoch,
        submission.toolchain_profile_id,
        package.leaderboard.formula_version,
    )
    # Through the shortest decimal of the float: 0.172, not 0.17199999999999998.
    return key, [Decimal(repr(value)) for value in sort_values(package.leaderboard, metrics)]


def _insert(
    submission: Submission, key: BoardKey, values: list[Decimal], ast: str | None, now: datetime
) -> Insert:
    """The statement that enters the Submit into the leaderboard as a new entry."""
    return insert(LeaderboardEntry).values(
        id=uuid7(),
        problem_id=key.problem_id,
        leaderboard_epoch=key.leaderboard_epoch,
        toolchain_profile_id=key.toolchain_profile_id,
        formula_version=key.formula_version,
        user_id=submission.user_id,
        submission_id=submission.id,
        sort_values=values,
        ast_hash=ast,
        submitted_at=submission.created_at,
        updated_at=now,
    )


async def rebuild(session: AsyncSession, user_ids: Collection[uuid.UUID], now: datetime) -> None:
    """Enter the users into the leaderboards again from their Submits, after a moderator hid or
    showed a solution or a user (FR-ADM-03): in each leaderboard the best accepted Submit that is
    not hidden, of a user who is not hidden; none, if there is no such Submit. The leaderboards
    that had or get an entry of the users are counted again.

    The caller holds the rows of the users for update, so that no Submit of theirs enters
    meanwhile. The rule is the ingestor's (`rank_submit`), applied to the stored stage results."""
    if not user_ids:
        return
    submissions = (
        await session.execute(
            select(Submission, ProblemVersion)
            .join(ProblemVersion, ProblemVersion.id == Submission.problem_version_id)
            .join(User, User.id == Submission.user_id)
            .where(
                Submission.user_id.in_(user_ids),
                Submission.is_public,
                Submission.is_hidden.is_(False),
                User.is_hidden.is_(False),
            )
        )
    ).all()
    results: dict[uuid.UUID, list[StageResult]] = {}
    stored = await session.scalars(
        select(StageRow).where(StageRow.submission_id.in_([found.id for found, _ in submissions]))
    )
    for row in stored:
        results.setdefault(row.submission_id, []).append(
            StageResult(
                key=row.stage_key,
                type=row.stage_type,
                ordinal=row.ordinal,
                status=row.status,  # type: ignore[arg-type]  # a stage_status value
                metrics=row.metrics or {},
            )
        )
    # The entry of a user in a leaderboard: lower sort_values, then the earlier Submit.
    best: dict[tuple[uuid.UUID, BoardKey], tuple[list[Decimal], datetime, Submission]] = {}
    for submission, version in submissions:
        assert submission.user_id is not None
        entry = _entry(submission, version, results.get(submission.id, []))
        if entry is None:
            continue
        key, values = entry
        known = best.get((submission.user_id, key))
        if known is None or (values, submission.created_at) < (known[0], known[1]):
            best[submission.user_id, key] = (values, submission.created_at, submission)
    keys = {key for _, key in best}
    for user_id in user_ids:
        keys.update(await boards_of(session, user_id))
    ordered = sorted(keys)
    await lock(session, ordered)
    await session.execute(delete(LeaderboardEntry).where(LeaderboardEntry.user_id.in_(user_ids)))
    for (_, key), (values, _, submission) in best.items():
        await session.execute(_insert(submission, key, values, submission.ast_hash, now))
    for key in ordered:
        await _recount(session, key, now)


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
    await lock(session, ordered)
    for key in ordered:
        await _recount(session, key, now)


async def lock(session: AsyncSession, keys: Sequence[BoardKey]) -> None:
    """Take the locks of the leaderboards, in the order of their keys."""
    for key in sorted(keys):
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
    entry of the author is this Submit or a better one. None if the Submit is not public or is
    hidden, its problem has no leaderboard, or the leaderboard is no longer the current one
    (another epoch, formula or default profile)."""
    if not submission.is_public or submission.is_hidden or submission.user_id is None:
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


def current_boards() -> Subquery:
    """The leaderboards pages show now, as `current_key` finds them, of every published problem:
    `problem_id`, `version_id` (the current version), `leaderboard_epoch`, `formula_version` and
    `toolchain_profile_id` (the default profile of its language). A problem without a formula
    has a null `formula_version` and matches no entry."""
    version = aliased(ProblemVersion, name="current_version")
    return (
        select(
            Problem.id.label("problem_id"),
            version.id.label("version_id"),
            version.leaderboard_epoch,
            cast(version.manifest["leaderboard"]["formula_version"].astext, Integer).label(
                "formula_version"
            ),
            ToolchainProfile.id.label("toolchain_profile_id"),
        )
        .join(version, version.id == Problem.current_version_id)
        .join(
            ToolchainProfile,
            and_(ToolchainProfile.language == version.language, ToolchainProfile.is_default),
        )
        .where(Problem.is_published)
        .subquery("current_board")
    )


def in_board(boards: Subquery) -> ColumnElement[bool]:
    """An entry of one of the leaderboards of `current_boards()`."""
    return and_(
        LeaderboardEntry.problem_id == boards.c.problem_id,
        LeaderboardEntry.leaderboard_epoch == boards.c.leaderboard_epoch,
        LeaderboardEntry.toolchain_profile_id == boards.c.toolchain_profile_id,
        LeaderboardEntry.formula_version == boards.c.formula_version,
    )


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
