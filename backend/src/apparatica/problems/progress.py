"""Which problems a signed-in user solved or tried (FR-CAT-03, FR-USR-06).

Any check that ends tries the problem, an accepted Submit solves it, and a solved problem stays
solved: the rules of the history a guest's browser keeps. The ingestor records a check in the
transaction that stores its verdict, so the status changes as soon as the check ends; the catalogue
and the profile read it.
"""

import uuid
from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.problems.models import ProblemVersion, UserProblemStatus

ACCEPTED = ("accepted", "accepted_with_warnings")


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
