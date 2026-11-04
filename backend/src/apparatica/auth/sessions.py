"""Server-side sessions (FR-AUTH-04, ADR-0010).

A login gives the browser a random token in the cookie `ap_session` (httpOnly, SameSite=Lax); the
table `sessions` keeps its sha256 only. A session lasts `session_ttl_s` (30 days) from its last
use: a request renews it at most once in `RENEW_EVERY`, moving the expiry of the row and the cookie.
Logout deletes the row, so an ended session is not accepted again. Sessions of an account past
its `delete_at` are not accepted either: the ingestor deletes the account soon after (FR-USR-05).

Sessions found in the database are cached in valkey-cache for `CACHE_TTL_S`; ending a session
deletes its entry. An unreachable cache sends every lookup to the database.
"""

import hashlib
import json
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Annotated

import redis.asyncio
import structlog
from fastapi import Depends, Request, Response
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.auth.models import User, UserSession
from apparatica.core.db import Database
from apparatica.core.errors import ApiError, ErrorCode

log = structlog.get_logger(__name__)

COOKIE = "ap_session"
RENEW_EVERY = timedelta(hours=1)  # how fresh last_seen_at is; also spares a write per request
CACHE_TTL_S = 60
TOKEN_MAX_LENGTH = 128  # a longer cookie is not a token of ours
USER_AGENT_MAX_LENGTH = 512
Clock = Callable[[], datetime]


def _now() -> datetime:
    return datetime.now(UTC)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class SessionInfo:
    id_hash: str
    user_id: uuid.UUID
    expires_at: datetime
    last_seen_at: datetime
    delete_at: datetime | None = None  # of the account
    renewed: bool = False  # by this lookup: the cookie is to be set again


class Sessions:
    def __init__(
        self,
        database: Database,
        cache: redis.asyncio.Redis | None,
        *,
        ttl_s: int,
        secure: bool,
        clock: Clock = _now,
    ) -> None:
        self._database, self._cache = database, cache
        self._ttl = timedelta(seconds=ttl_s)
        self._secure = secure
        self._clock = clock

    async def start(self, session: AsyncSession, user_id: uuid.UUID, user_agent: str | None) -> str:
        """Add a session of the user to the transaction of `session`; returns its token for
        `set_cookie` once the transaction commits."""
        token = secrets.token_urlsafe(32)
        now = self._clock()
        session.add(
            UserSession(
                id_hash=token_hash(token),
                user_id=user_id,
                created_at=now,
                expires_at=now + self._ttl,
                last_seen_at=now,
                user_agent=user_agent[:USER_AGENT_MAX_LENGTH] if user_agent else None,
            )
        )
        return token

    async def find(self, token: str) -> SessionInfo | None:
        """The live session of a token, renewed when due."""
        if not token or len(token) > TOKEN_MAX_LENGTH:
            return None
        id_hash = token_hash(token)
        found = await self._cached(id_hash)
        if found is None:
            async with self._database.sessions() as session:
                row = (
                    await session.execute(
                        select(UserSession, User.delete_at)
                        .join(User, User.id == UserSession.user_id)
                        .where(UserSession.id_hash == id_hash)
                    )
                ).first()
            if row is None:
                return None
            user_session, delete_at = row
            found = SessionInfo(
                id_hash,
                user_session.user_id,
                user_session.expires_at,
                user_session.last_seen_at,
                delete_at,
            )
            await self._remember(found)
        now = self._clock()
        if found.expires_at <= now:
            return None
        # A deletion asked meanwhile is 7 days away: the cached time may lag behind it.
        if found.delete_at is not None and found.delete_at <= now:
            return None
        if now - found.last_seen_at >= RENEW_EVERY:
            return await self._renew(found, now)
        return found

    async def end(self, token: str) -> None:
        if not token or len(token) > TOKEN_MAX_LENGTH:
            return
        id_hash = token_hash(token)
        async with self._database.sessions.begin() as session:
            await session.execute(delete(UserSession).where(UserSession.id_hash == id_hash))
        await self._forget(id_hash)

    async def end_all(self, user_id: uuid.UUID) -> None:
        async with self._database.sessions.begin() as session:
            ended = await session.scalars(
                delete(UserSession)
                .where(UserSession.user_id == user_id)
                .returning(UserSession.id_hash)
            )
            hashes = ended.all()
        await self._forget(*hashes)

    def set_cookie(self, response: Response, token: str) -> None:
        response.set_cookie(
            COOKIE,
            token,
            max_age=int(self._ttl.total_seconds()),
            path="/",
            secure=self._secure,
            httponly=True,
            samesite="lax",
        )

    def clear_cookie(self, response: Response) -> None:
        response.delete_cookie(COOKIE, path="/", secure=self._secure, httponly=True, samesite="lax")

    async def _renew(self, found: SessionInfo, now: datetime) -> SessionInfo | None:
        expires_at = now + self._ttl
        async with self._database.sessions.begin() as session:
            result = await session.execute(
                update(UserSession)
                .where(UserSession.id_hash == found.id_hash)
                .values(last_seen_at=now, expires_at=expires_at)
                .returning(UserSession.id_hash)
            )
            ended = result.first() is None  # meanwhile
        if ended:
            await self._forget(found.id_hash)
            return None
        renewed = replace(found, expires_at=expires_at, last_seen_at=now)
        await self._remember(renewed)
        return replace(renewed, renewed=True)

    async def _cached(self, id_hash: str) -> SessionInfo | None:
        if self._cache is None:
            return None
        try:
            raw = await self._cache.get(_key(id_hash))
        except (redis.RedisError, OSError) as error:
            log.warning("session cache not read", error=str(error))
            return None
        if raw is None:
            return None
        value = json.loads(raw)
        delete_at = value.get("delete_at")
        return SessionInfo(
            id_hash,
            uuid.UUID(value["user_id"]),
            datetime.fromisoformat(value["expires_at"]),
            datetime.fromisoformat(value["last_seen_at"]),
            datetime.fromisoformat(delete_at) if delete_at is not None else None,
        )

    async def _remember(self, found: SessionInfo) -> None:
        if self._cache is None:
            return
        value = {
            "user_id": str(found.user_id),
            "expires_at": found.expires_at.isoformat(),
            "last_seen_at": found.last_seen_at.isoformat(),
            "delete_at": found.delete_at.isoformat() if found.delete_at is not None else None,
        }
        try:
            await self._cache.set(_key(found.id_hash), json.dumps(value), ex=CACHE_TTL_S)
        except (redis.RedisError, OSError) as error:
            log.warning("session cache not written", error=str(error))

    async def _forget(self, *hashes: str) -> None:
        if self._cache is None or not hashes:
            return
        try:
            await self._cache.delete(*(_key(id_hash) for id_hash in hashes))
        except (redis.RedisError, OSError) as error:
            # The ended sessions stay accepted from the cache for up to CACHE_TTL_S.
            log.warning("session cache not cleared", error=str(error))


def _key(id_hash: str) -> str:
    return f"session:{id_hash}"


async def current_session(request: Request, response: Response) -> SessionInfo | None:
    """FastAPI dependency: the session of the request; a renewed one gets its cookie again."""
    token = request.cookies.get(COOKIE)
    if token is None:
        return None
    sessions: Sessions = request.app.state.sessions
    found = await sessions.find(token)
    if found is not None and found.renewed:
        sessions.set_cookie(response, token)
    return found


CurrentSession = Annotated[SessionInfo | None, Depends(current_session)]


async def signed_in(session: CurrentSession) -> SessionInfo:
    """FastAPI dependency of a route for signed-in users: UNAUTHENTICATED without a session."""
    if session is None:
        raise ApiError(ErrorCode.UNAUTHENTICATED, "Sign in to continue")
    return session


SignedIn = Annotated[SessionInfo, Depends(signed_in)]
