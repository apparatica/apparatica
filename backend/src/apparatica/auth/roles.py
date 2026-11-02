"""Roles of users (FR-AUTH-07): `user`, `author` (of problems), `moderator`, `admin`; a guest has
none. A role is read from `users` at each request that needs it, so a changed role applies at once.
An administrator changes roles: `apparatica-admin users set-role` now, the admin panel in T3.12.
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.auth.models import User
from apparatica.auth.schemas import Role
from apparatica.auth.sessions import SignedIn
from apparatica.core.db import get_session
from apparatica.core.errors import ApiError, ErrorCode

ADMIN: Role = "admin"


def require_role(*roles: Role) -> Callable[..., Awaitable[User]]:
    """A FastAPI dependency: the signed-in user with one of `roles`, or an administrator, who may
    do everything. UNAUTHENTICATED without a session, FORBIDDEN with another role."""
    allowed = {*roles, ADMIN}

    async def dependency(
        signed_in: SignedIn, session: Annotated[AsyncSession, Depends(get_session)]
    ) -> User:
        user = await session.get(User, signed_in.user_id)
        if user is None:  # deleted after the lookup of the session
            raise ApiError(ErrorCode.UNAUTHENTICATED, "Sign in to continue")
        if user.role not in allowed:
            raise ApiError(ErrorCode.FORBIDDEN, "Not allowed for the role of the user")
        return user

    return dependency


async def set_role(session: AsyncSession, nick: str, role: Role) -> uuid.UUID | None:
    """Give the user `nick` the role; None: no such user."""
    user_id: uuid.UUID | None = await session.scalar(
        update(User).where(User.nick == nick).values(role=role).returning(User.id)
    )
    return user_id
