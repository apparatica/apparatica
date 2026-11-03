"""Accounts: the user as the API shows it to themselves (`Me`), accounts that a first login
creates with the legal documents it accepts (FR-AUTH-06), and the nick that the user changes once
in 30 days (FR-AUTH-02)."""

import re
import secrets
import string
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.auth.models import Consent, Identity, User
from apparatica.auth.schemas import Me, Role
from apparatica.core.errors import ApiError, ErrorCode
from apparatica.core.ids import uuid7

NICK_ALPHABET = string.ascii_lowercase + string.digits
NICK_LENGTH = (3, 24)  # ck_users_nick_format
SUFFIX_LENGTH = 4
DISPLAY_NAME_LENGTH = 60  # DisplayName
ATTEMPTS = 5  # of a free nick, or of finding the account a concurrent login created
NICK_CHANGE_EVERY = timedelta(days=30)  # FR-AUTH-02


def me(user: User, now: datetime | None = None) -> Me:
    return Me(
        id=user.id,
        nick=user.nick,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        email=user.email,
        role=cast(Role, user.role),  # ck_users_role
        created_at=user.created_at,
        nick_change_available_at=nick_change_available_at(user, now or datetime.now(UTC)),
        delete_at=None,  # deletion arrives in T2.9
    )


def nick_change_available_at(user: User, now: datetime) -> datetime | None:
    """When the user may change the nick again; None: now. The nick of the first login does not
    count: an account with the random nick of an email login renames itself at once."""
    if user.nick_changed_at is None:
        return None
    available_at = user.nick_changed_at + NICK_CHANGE_EVERY
    return available_at if available_at > now else None


async def change_nick(session: AsyncSession, user: User, nick: str, now: datetime) -> None:
    """Give `user` (locked by the caller) another nick. The old nick is free at once; the same nick
    changes nothing. NICK_CHANGE_TOO_SOON within 30 days of the last change, NICK_TAKEN for a nick
    of another account."""
    if nick == user.nick:
        return
    available_at = nick_change_available_at(user, now)
    if available_at is not None:
        raise ApiError(
            ErrorCode.NICK_CHANGE_TOO_SOON,
            "The nick changes once in 30 days",
            params={"available_at": available_at.isoformat()},
        )
    try:
        async with session.begin_nested():  # a taken nick, also by a concurrent change
            user.nick, user.nick_changed_at = nick, now
            await session.flush()
    except IntegrityError:
        raise ApiError(ErrorCode.NICK_TAKEN, f"The nick '{nick}' is taken") from None


def random_nick() -> str:
    """A nick that tells nothing about the person, e.g. `user-k3f9qz`: an email login has no nick
    to offer, and its address is not public. The user changes it in the settings."""
    return "user-" + _random(6)


def _random(length: int) -> str:
    return "".join(secrets.choice(NICK_ALPHABET) for _ in range(length))


def nicks(preferred: str | None) -> Iterator[str]:
    """Nicks for a new account, best first (FR-AUTH-02): the nick of the provider in the form of
    nicks, then with a random suffix (`ada-x7k2`) while it is taken; random without a nick."""
    low, high = NICK_LENGTH
    base = re.sub(r"[^a-z0-9_.-]+", "-", (preferred or "").lower()).strip("-_.")
    if not base:
        while True:
            yield random_nick()
    if len(base) >= low:
        yield base[:high]
    base = base[: high - SUFFIX_LENGTH - 1].rstrip("-_.")
    while True:
        yield f"{base}-{_random(SUFFIX_LENGTH)}"


async def sign_up(
    session: AsyncSession,
    provider: str,
    subject: str,
    *,
    email: str | None,
    documents: Mapping[str, date],
    nick: str | None = None,
    display_name: str | None = None,
    avatar_url: str | None = None,
) -> tuple[User, bool]:
    """The user of an identity, created with it at the first login; True when created. The
    identity is the key: accounts are not joined by email (ADR-0010). The nick, the name and the
    avatar of the provider are those of a new account only: later logins do not change them. A new
    account accepts the `documents` (key → version): the login page says that continuing accepts
    them (FR-AUTH-06)."""
    query = select(User).join(Identity).where(Identity.provider == provider)
    candidates = nicks(nick)
    name = (display_name or "").strip()[:DISPLAY_NAME_LENGTH].rstrip() or None
    for _ in range(ATTEMPTS):
        found = await session.scalar(query.where(Identity.subject == subject))
        if found is not None:
            return found, False
        user = User(
            id=uuid7(),
            nick=next(candidates),
            display_name=name,
            avatar_url=avatar_url,
            email=email,
            role="user",
        )
        try:
            async with session.begin_nested():  # a taken nick or a concurrent login
                session.add(user)
                await session.flush()
                session.add(
                    Identity(
                        id=uuid7(), user_id=user.id, provider=provider, subject=subject, email=email
                    )
                )
                session.add_all(
                    Consent(user_id=user.id, document=key, version=version)
                    for key, version in documents.items()
                )
                await session.flush()
        except IntegrityError:
            continue
        await session.refresh(user)  # created_at of the database
        return user, True
    raise RuntimeError(f"no account for a {provider} login after {ATTEMPTS} attempts")
