"""Public profiles (FR-USR-04): the account, the problems it solved, its place in the global
leaderboard, the places it holds in the leaderboards of problems and its public solutions. The
activity arrives in phase 4."""

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.auth.models import User
from apparatica.leaderboards.places import best_places
from apparatica.leaderboards.rating import rating_of
from apparatica.leaderboards.solutions import count_user_solutions
from apparatica.problems.models import Problem, ProblemVersion
from apparatica.problems.progress import ACCEPTED, progress_of
from apparatica.submissions.models import Submission
from apparatica.users.schemas import DifficultyProgress, Profile, SolvedProblem, SubmitCount

# Verdicts of a Submit that count for «Принято»: not cancelled, no internal error.
VERDICTS = (*ACCEPTED, "wrong_answer", "compile_error", "limit_exceeded", "forbidden_construct")


async def find_user(session: AsyncSession, nick: str) -> User | None:
    """The account of a public profile; an account being deleted is hidden at once (FR-USR-05),
    as one hidden by a moderator (FR-ADM-03)."""
    return await session.scalar(
        select(User).where(User.nick == nick, User.delete_at.is_(None), User.is_hidden.is_(False))
    )


async def get_profile(
    session: AsyncSession, nick: str, difficulty_order: Sequence[str], today: date
) -> Profile | None:
    user = await find_user(session, nick)
    if user is None:
        return None
    progress = await progress_of(session, user.id, difficulty_order)
    return Profile(
        nick=user.nick,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
        progress=[
            DifficultyProgress(difficulty=key, solved=solved, total=total)
            for key, solved, total in progress.levels
        ],
        solved=[
            SolvedProblem(
                slug=item.slug,
                number=item.number,
                title=item.title,
                difficulty=item.difficulty,
                solved_at=item.solved_at,
            )
            for item in progress.solved
        ],
        rating=await rating_of(session, user.id, today),
        best_places=await best_places(session, user.id),
        solutions=await count_user_solutions(session, user.id),
        submits=await submit_count(session, user.id),
    )


async def submit_count(session: AsyncSession, user_id: uuid.UUID) -> SubmitCount:
    """Submits of the user with a verdict on published problems."""
    accepted, total = (
        await session.execute(
            select(func.count().filter(Submission.status.in_(ACCEPTED)), func.count())
            .select_from(Submission)
            .join(ProblemVersion, ProblemVersion.id == Submission.problem_version_id)
            .join(Problem, Problem.id == ProblemVersion.problem_id)
            .where(
                Submission.user_id == user_id,
                Submission.kind == "submit",
                Submission.status.in_(VERDICTS),
                Problem.is_published,
            )
        )
    ).one()
    return SubmitCount(accepted=accepted, total=total)
