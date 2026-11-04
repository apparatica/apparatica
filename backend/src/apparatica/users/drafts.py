"""Drafts of signed-in users on the server (FR-EDT-02): one per problem, the last save wins. The
browser keeps its own copy as a backup and compares the times of the two."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.core.errors import ApiError, ErrorCode
from apparatica.core.platform import SolutionLimits
from apparatica.problems.models import Problem
from apparatica.submissions.service import check_size
from apparatica.users.models import Draft as DraftRow
from apparatica.users.schemas import Draft, DraftSave


async def get_draft(session: AsyncSession, user_id: uuid.UUID, slug: str) -> Draft | None:
    """The draft of a published problem."""
    row = await session.scalar(
        select(DraftRow)
        .join(Problem, Problem.id == DraftRow.problem_id)
        .where(DraftRow.user_id == user_id, Problem.slug == slug, Problem.is_published)
    )
    if row is None:
        return None
    return Draft(code=row.code, problem_version=row.problem_version, updated_at=row.updated_at)


async def save_draft(
    session: AsyncSession,
    user_id: uuid.UUID,
    slug: str,
    body: DraftSave,
    *,
    limits: SolutionLimits,
    now: datetime,
) -> Draft:
    """Store the draft; NOT_FOUND for a problem that is not published, CODE_TOO_LARGE for code over
    the limits of a solution: it could not be sent anyway."""
    check_size(body.code, limits)
    problem_id = await session.scalar(
        select(Problem.id).where(Problem.slug == slug, Problem.is_published)
    )
    if problem_id is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"No published problem {slug!r}")
    values = {"code": body.code, "problem_version": body.problem_version, "updated_at": now}
    statement = insert(DraftRow).values(user_id=user_id, problem_id=problem_id, **values)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[DraftRow.user_id, DraftRow.problem_id], set_=values
        )
    )
    await session.commit()
    return Draft(code=body.code, problem_version=body.problem_version, updated_at=now)
