"""Schemas of login and of the account it creates (specs/05 §3, phase 2)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

# OAuth providers of the login routes; VK ID, Yandex ID and Google join in phase 4.
OAuthProvider = Literal["github"]
# Where to go after login: a path of the site, never another origin (`//host`, `/\host`).
NextPath = Annotated[
    str,
    Field(
        max_length=2048,
        pattern=r"^/([^/\\\s]\S*)?$",
        examples=["/problems/sync-fifo"],
        description="Path of the site to return to after login",
    ),
]
Email = Annotated[
    str,
    Field(
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        json_schema_extra={"format": "email"},
        examples=["name@example.com"],
    ),
]


Role = Literal["user", "author", "moderator", "admin"]
Nick = Annotated[
    str,
    Field(
        min_length=3,
        max_length=24,
        pattern=r"^[a-z0-9_.-]+$",
        examples=["ada"],
        description="Unique, lowercase; the profile is /u/<nick>",
    ),
]
# Spaces around the name are dropped; a name of spaces only is no name.
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class UserRef(BaseModel):
    """A user as others see them: an author in leaderboards and solutions."""

    nick: Nick
    display_name: str | None
    avatar_url: str | None
    deleted: bool = Field(
        default=False,
        description="The solution of a deleted account (ОВ-12): shown as «удалённый участник», "
        "the nick is not a profile",
    )


class Me(BaseModel):
    """The signed-in user."""

    id: uuid.UUID
    nick: Nick
    display_name: str | None
    avatar_url: str | None
    email: str | None = Field(description="From email login or the provider; never public")
    role: Role
    created_at: datetime
    nick_change_available_at: datetime | None = Field(
        description="When the nick may change again (once in 30 days); null: now"
    )
    delete_at: datetime | None = Field(
        description="When the account will be deleted; null: no deletion requested (FR-USR-05)"
    )


class EmailLoginRequest(BaseModel):
    email: Email
    next: NextPath | None = None
    captcha: str | None = Field(
        default=None,
        max_length=4096,
        description="Solved ALTCHA challenge after CAPTCHA_REQUIRED (base64 JSON of the widget)",
    )


class EmailLoginVerify(BaseModel):
    token: str = Field(
        min_length=16, max_length=128, description="The token of the link from the letter"
    )


class EmailLogin(BaseModel):
    """A signed-in user after a login link: the session cookie is set."""

    user: Me
    created: bool = Field(description="The account was created by this login (FR-AUTH-02)")
    next: NextPath | None = Field(description="`next` of the link request")
