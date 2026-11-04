"""Which problems a signed-in user solved or tried (FR-CAT-03, FR-USR-06).

Any check that ends tries the problem, an accepted Submit solves it, and a solved problem stays
solved: the rules of the history a guest's browser keeps. The ingestor records a check in the
transaction that stores its verdict, so the status changes as soon as the check ends; the catalogue
and the profile read it.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.problems.models import Problem, ProblemVersion, UserProblemStatus

ACCEPTED = ("accepted", "accepted_with_warnings")


@dataclass(frozen=True)
class Solved:
    slug: str
    number: int
    title: str
    difficulty: str
    solved_at: datetime


@dataclass(frozen=True)
class Progress:
    """`levels`: (level, solved, published problems) in the order of the configuration; `solved`:
    the published problems the user solved, newest first."""

    levels: list[tuple[str, int, int]]
    solved: list[Solved]


async def progress_of(
    session: AsyncSession, user_id: uuid.UUID, difficulty_order: Sequence[str]
) -> Progress:
    """What the profile of the user shows (FR-USR-04): an unpublished problem is not counted."""
    current = (
        select(Problem, ProblemVersion)
        .join(ProblemVersion, ProblemVersion.id == Problem.current_version_id)
        .where(Problem.is_published)
    )
    rows = await session.execute(
        current.add_columns(UserProblemStatus.first_solved_at)
        .join(UserProblemStatus, UserProblemStatus.problem_id == Problem.id)
        .where(UserProblemStatus.user_id == user_id, UserProblemStatus.status == "solved")
        .order_by(UserProblemStatus.first_solved_at.desc(), Problem.number)
    )
    solved = [
        Solved(problem.slug, problem.number, version.title, version.difficulty, solved_at)
        for problem, version, solved_at in rows
    ]
    counts = await session.execute(
        current.with_only_columns(ProblemVersion.difficulty, func.count()).group_by(
            ProblemVersion.difficulty
        )
    )
    totals = {level: count for level, count in counts}
    levels = [
        (key, sum(item.difficulty == key for item in solved), totals.get(key, 0))
        for key in difficulty_order
    ]
    return Progress(levels, solved)


async def record_check(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    problem_version_id: uuid.UUID,
    submission_id: uuid.UUID,
    kind: str,
    status: str,
    finished_at: datetime,
) -> None:
    """A check of the user ended with `status`."""
    solved = kind == "submit" and status in ACCEPTED
    problem_id = (
        select(ProblemVersion.problem_id)
        .where(ProblemVersion.id == problem_version_id)
        .scalar_subquery()
    )
    statement = insert(UserProblemStatus).values(
        user_id=user_id,
        problem_id=problem_id,
        status="solved" if solved else "attempted",
        first_solved_at=finished_at if solved else None,
        last_submission_id=submission_id,
    )
    new = statement.excluded
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[UserProblemStatus.user_id, UserProblemStatus.problem_id],
            set_={
                "status": case((UserProblemStatus.status == "solved", "solved"), else_=new.status),
                "first_solved_at": func.coalesce(
                    UserProblemStatus.first_solved_at, new.first_solved_at
                ),
                "last_submission_id": new.last_submission_id,
            },
        )
    )
