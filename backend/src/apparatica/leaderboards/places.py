"""The places a user holds in the leaderboards of problems, for the profile (FR-USR-04, T3.10).

A place is held in a leaderboard that pages show now (`ranking.current_boards`): the entry of the
user leads its group and has a rank. A follower of a group (a solution with the same syntax tree
as an earlier one) holds no place of its own (FR-LB-04), as in the global leaderboard.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from apparatica.leaderboards.boards import formula_of
from apparatica.leaderboards.models import LeaderboardEntry
from apparatica.leaderboards.ranking import current_boards, in_board
from apparatica.leaderboards.schemas import BestPlace, ProblemRef
from apparatica.problems.models import Problem, ProblemVersion

BEST_PLACES = 10  # shown in a profile


async def best_places(
    session: AsyncSession, user_id: uuid.UUID, limit: int = BEST_PLACES
) -> list[BestPlace]:
    """The places of the user, the best first: by the place, then the larger leaderboard, then
    the number of the problem."""
    boards = current_boards()
    other = aliased(LeaderboardEntry, name="other")
    entries = (
        select(func.count())
        .where(
            other.problem_id == LeaderboardEntry.problem_id,
            other.leaderboard_epoch == LeaderboardEntry.leaderboard_epoch,
            other.toolchain_profile_id == LeaderboardEntry.toolchain_profile_id,
            other.formula_version == LeaderboardEntry.formula_version,
        )
        .correlate(LeaderboardEntry)
        .scalar_subquery()
        .label("entries")
    )
    rows = await session.execute(
        select(LeaderboardEntry, entries, Problem, ProblemVersion)
        .join(boards, in_board(boards))
        .join(Problem, Problem.id == LeaderboardEntry.problem_id)
        .join(ProblemVersion, ProblemVersion.id == boards.c.version_id)
        .where(LeaderboardEntry.user_id == user_id, LeaderboardEntry.rank.is_not(None))
        .order_by(LeaderboardEntry.rank, entries.desc(), Problem.number)
        .limit(limit)
    )
    found = []
    for entry, count, problem, version in rows:
        formula = formula_of(version)
        assert entry.rank is not None  # by the query
        assert formula is not None  # a board of `current_boards` has one
        found.append(
            BestPlace(
                problem=ProblemRef(
                    slug=problem.slug,
                    number=problem.number,
                    title=version.title,
                    difficulty=version.difficulty,
                ),
                rank=entry.rank,
                entries=count,
                solution_id=entry.submission_id,
                order=formula.order,
            )
        )
    return found
