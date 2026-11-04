"""Public profiles (FR-USR-04): the account and the problems it solved. Places in the leaderboards
and public solutions arrive in phase 3, the activity in phase 4."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.auth.models import User
from apparatica.problems.progress import progress_of
from apparatica.users.schemas import DifficultyProgress, Profile, SolvedProblem


async def get_profile(
    session: AsyncSession, nick: str, difficulty_order: Sequence[str]
) -> Profile | None:
    user = await session.scalar(select(User).where(User.nick == nick))
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
    )
