"""The global leaderboard of users (FR-LB-05, ADR-0006): points for all time by the formula of
`config/rating.yaml`.

- A user gets the points of the level of every published problem they solved (an accepted Submit
  of any version; the level of the current version) and the bonus of a place 1, 2, 3 in the
  leaderboard of a problem that pages show now (current epoch and formula, default profile). A
  shared place gives the bonus to each of its holders; a follower of a group (the same syntax tree
  as an earlier solution) holds no place and gets none.
- Equal points: whoever reached them first ranks higher (ADR-0006). The moment is read from the
  data: the latest first solution of a counted problem or Submit that holds a counted place, so a
  count depends on nothing but the tables and gives the same places when repeated. The id of the
  user breaks what is left: places are unique.
- `user_ratings` is counted again by one statement, under a transaction advisory lock: by the
  ingestor after an accepted Submit and after an account is deleted, and by its periodic task,
  which catches new versions, a new default profile and a new formula. Only rows that change are
  written. The periodic task also keeps the place of each user at the start of a day (UTC):
  «за неделю» compares it with the place 7 days ago.
"""

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import Integer, and_, bindparam, delete, func, literal, select, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from apparatica.auth.models import User
from apparatica.auth.schemas import UserRef
from apparatica.core.platform import RatingFormula
from apparatica.leaderboards.models import UserRating, UserRatingSnapshot
from apparatica.leaderboards.schemas import GlobalLeaderboard, PointsFormula, RatingRow

WEEK = timedelta(days=7)
SNAPSHOT_DAYS = 14  # a missed day falls back to an older snapshot, kept this long
AROUND = 2  # rows above and below the own one (FR-LB-05)
_LOCK = "rating:global"

_RECOUNT = text("""
WITH current AS (
    SELECT problem.id AS problem_id,
           version.difficulty,
           version.leaderboard_epoch,
           (version.manifest -> 'leaderboard' ->> 'formula_version')::int AS formula_version,
           profile.id AS toolchain_profile_id
    FROM problems AS problem
    JOIN problem_versions AS version ON version.id = problem.current_version_id
    LEFT JOIN toolchain_profiles AS profile
        ON profile.language = version.language AND profile.is_default
    WHERE problem.is_published
), levels AS (
    SELECT status.user_id, current.difficulty, count(*) AS solved, max(status.first_solved_at) AS at
    FROM user_problem_status AS status
    JOIN current USING (problem_id)
    WHERE status.status = 'solved'
    GROUP BY status.user_id, current.difficulty
), solved AS (
    SELECT user_id,
           jsonb_object_agg(difficulty, solved) AS by_level,
           sum(solved * coalesce((CAST(:points AS jsonb) ->> difficulty)::int, 0)) AS points,
           max(at) AS at
    FROM levels
    GROUP BY user_id
), places AS (
    SELECT entry.user_id,
           sum((CAST(:places AS int[]))[entry.rank]) AS points,
           max(entry.submitted_at) AS at
    FROM leaderboard_entries AS entry
    JOIN current USING (problem_id, leaderboard_epoch, toolchain_profile_id, formula_version)
    WHERE (CAST(:places AS int[]))[entry.rank] > 0
    GROUP BY entry.user_id
), rating AS (
    -- A place needs an accepted Submit, which solves the problem.
    SELECT solved.user_id,
           solved.by_level,
           solved.points + coalesce(places.points, 0) AS points,
           greatest(solved.at, places.at) AS reached_at
    FROM solved
    LEFT JOIN places USING (user_id)
), ranked AS (
    SELECT rating.*, row_number() OVER (ORDER BY points DESC, reached_at, user_id) AS rank
    FROM rating
    WHERE points > 0
), gone AS (
    DELETE FROM user_ratings AS old
    WHERE NOT EXISTS (SELECT FROM ranked WHERE ranked.user_id = old.user_id)
)
INSERT INTO user_ratings AS old
    (user_id, points, solved_by_difficulty, reached_at, rank, formula_version, updated_at)
SELECT user_id, points, by_level, reached_at, rank, :formula_version, :now
FROM ranked
ON CONFLICT (user_id) DO UPDATE
SET points = excluded.points,
    solved_by_difficulty = excluded.solved_by_difficulty,
    reached_at = excluded.reached_at,
    rank = excluded.rank,
    formula_version = excluded.formula_version,
    updated_at = excluded.updated_at
WHERE (old.points, old.solved_by_difficulty, old.reached_at, old.rank, old.formula_version)
    IS DISTINCT FROM (excluded.points, excluded.solved_by_difficulty, excluded.reached_at,
                      excluded.rank, excluded.formula_version)
""").bindparams(
    bindparam("points", type_=JSONB),
    bindparam("places", type_=ARRAY(Integer)),
)


async def lock(session: AsyncSession) -> None:
    """Counts of the global leaderboard go one at a time. A transaction that also changes
    leaderboards of problems takes their locks first."""
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended(literal(_LOCK), 0)))
    )


async def recount(session: AsyncSession, formula: RatingFormula, now: datetime) -> None:
    """Count the points and places of every user again."""
    await lock(session)
    await session.execute(
        _RECOUNT,
        {
            "points": formula.solved,
            "places": formula.places,
            "formula_version": formula.formula_version,
            "now": now,
        },
    )


async def snapshot(session: AsyncSession, today: date) -> int:
    """Keep the places at the start of the day, once a day; returns how many rows it wrote.
    Snapshots older than SNAPSHOT_DAYS are deleted."""
    await lock(session)
    await session.execute(
        delete(UserRatingSnapshot).where(
            UserRatingSnapshot.day < today - timedelta(days=SNAPSHOT_DAYS)
        )
    )
    taken = await session.scalar(
        select(func.count()).select_from(UserRatingSnapshot).where(UserRatingSnapshot.day == today)
    )
    if taken:
        return 0
    rows = select(literal(today), UserRating.user_id, UserRating.rank)
    result = await session.execute(
        insert(UserRatingSnapshot).from_select(["day", "user_id", "rank"], rows)
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def global_leaderboard(
    session: AsyncSession,
    formula: RatingFormula,
    *,
    viewer: uuid.UUID | None,
    page: int,
    per_page: int,
    today: date,
) -> GlobalLeaderboard:
    """A page of the global leaderboard; `me` and the rows around it for a signed-in viewer."""
    week_ago = await session.scalar(
        select(func.max(UserRatingSnapshot.day)).where(UserRatingSnapshot.day <= today - WEEK)
    )
    before = aliased(UserRatingSnapshot)
    rows = (
        select(UserRating, User.nick, User.display_name, User.avatar_url, before.rank)
        .join(User, User.id == UserRating.user_id)
        .outerjoin(before, and_(before.user_id == UserRating.user_id, before.day == week_ago))
        .order_by(UserRating.rank)
    )
    levels = list(formula.solved)

    def row(found: tuple[UserRating, str, str | None, str | None, int | None]) -> RatingRow:
        rating, nick, display_name, avatar_url, rank_before = found
        return RatingRow(
            rank=rating.rank,
            user=UserRef(nick=nick, display_name=display_name, avatar_url=avatar_url),
            points=rating.points,
            solved={level: rating.solved_by_difficulty.get(level, 0) for level in levels},
            week_delta=None if rank_before is None else rank_before - rating.rank,
            is_me=rating.user_id == viewer,
        )

    first, last = (page - 1) * per_page + 1, page * per_page
    items = [
        row(found)
        for found in await session.execute(rows.where(UserRating.rank.between(first, last)))
    ]
    total = await session.scalar(select(func.count()).select_from(UserRating)) or 0
    me = None
    around: list[RatingRow] = []
    if viewer is not None:
        found = (await session.execute(rows.where(UserRating.user_id == viewer))).one_or_none()
        me = None if found is None else row(found)
    if me is not None and not first <= me.rank <= last:
        near = UserRating.rank.between(me.rank - AROUND, me.rank + AROUND)
        on_page = UserRating.rank.between(first, last)
        around = [row(found) for found in await session.execute(rows.where(near, ~on_page))]
    return GlobalLeaderboard(
        items=items,
        page=page,
        per_page=per_page,
        total=total,
        formula=PointsFormula(
            version=formula.formula_version, solved=formula.solved, places=formula.places
        ),
        me=me,
        around_me=around,
    )
