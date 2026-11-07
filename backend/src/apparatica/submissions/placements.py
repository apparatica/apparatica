"""The place of a submission in the leaderboard of its problem (FR-RUN-05).

`apparatica.leaderboards` keeps the leaderboards and stands above this module (specs/03 §3), so the
application passes its function in: `app.state.placement_of`.
"""

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.submissions.models import Submission
from apparatica.submissions.schemas import LeaderboardPlacement

type PlacementOf = Callable[[AsyncSession, Submission], Awaitable[LeaderboardPlacement | None]]
