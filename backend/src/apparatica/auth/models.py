"""Tables of accounts: users, their identities at login providers and sessions (specs/04 §4, Ф2).

The first login creates the user; deletion of a user cascades to its identities and sessions.
"""

import uuid
from datetime import datetime
from typing import get_args

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from apparatica.auth.schemas import Role
from apparatica.core.db import Base, created_at, uuid_pk

ROLES: tuple[str, ...] = get_args(Role)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # The pattern of Nick: profiles are /u/<nick>, and citext keeps them unique in any case.
        CheckConstraint("nick ~ '^[a-z0-9_.-]{3,24}$'", name="nick_format"),
        CheckConstraint(f"role IN ({', '.join(repr(role) for role in ROLES)})", name="role"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    nick: Mapped[str] = mapped_column(CITEXT, unique=True)
    display_name: Mapped[str | None]
    avatar_url: Mapped[str | None]
    email: Mapped[str | None] = mapped_column(CITEXT)  # never public
    role: Mapped[str] = mapped_column(server_default="user")
    created_at: Mapped[datetime] = created_at()


class Identity(Base):
    """A login of the user: an account at an OAuth provider, or an email address (`email`)."""

    __tablename__ = "identities"
    __table_args__ = (UniqueConstraint("provider", "subject"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str]
    subject: Mapped[str]  # the id of the account at the provider; the address for email
    email: Mapped[str | None]
    created_at: Mapped[datetime] = created_at()


class UserSession(Base):
    """A server-side session (ADR-0010): the cookie holds a random token, the table its hash."""

    __tablename__ = "sessions"
    __table_args__ = (CheckConstraint("id_hash ~ '^[0-9a-f]{64}$'", name="id_hash_sha256"),)

    id_hash: Mapped[str] = mapped_column(primary_key=True)  # sha256 of the token, hex
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = created_at()
    expires_at: Mapped[datetime] = mapped_column(index=True)  # moves on with use
    last_seen_at: Mapped[datetime]
    user_agent: Mapped[str | None]
