"""Accounts: the user as the API shows it to themselves (`Me`)."""

from typing import cast

from apparatica.auth.models import User
from apparatica.auth.schemas import Me, Role


def me(user: User) -> Me:
    return Me(
        id=user.id,
        nick=user.nick,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        email=user.email,
        role=cast(Role, user.role),  # ck_users_role
        created_at=user.created_at,
        nick_change_available_at=None,  # nick changes arrive in T2.4
        delete_at=None,  # deletion arrives in T2.9
    )
