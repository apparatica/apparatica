"""Login links (FR-AUTH-05, ADR-0010): a letter with a one-time link valid for 15 minutes.

The link is `<public_base_url>/login/email/verify#token=<token>`: a page of the site posts the
token, so neither server logs nor link previews see or spend it. The table `email_tokens` keeps the
sha256 of the token. A request always answers the same, whether the address has an account or not:
the first use of a link creates it.
"""

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from apparatica.auth.accounts import sign_up
from apparatica.auth.models import EmailToken, User
from apparatica.auth.sessions import TOKEN_MAX_LENGTH, Sessions
from apparatica.core.db import Database
from apparatica.core.mail import Letter, Mailer

PROVIDER = "email"  # identities.provider; the subject is the address
LINK_TTL = timedelta(minutes=15)
LINK = "{base}/login/email/verify#token={token}"
Clock = Callable[[], datetime]

# Templates of the letter by locale (specs/09 §1); the site speaks Russian only so far.
LOGIN_LETTER = {
    "ru": (
        "Вход в Apparatica",
        "Здравствуйте!\n\n"
        "Чтобы войти в Apparatica, откройте ссылку:\n\n"
        "{link}\n\n"
        "Ссылка действует {minutes} минут и сработает один раз. Если вы не запрашивали вход, "
        "просто не обращайте внимания на это письмо.\n",
    )
}


def _now() -> datetime:
    return datetime.now(UTC)


def normalize(email: str) -> str:
    """The form of an address in identities and rate limits: one account whatever its case."""
    return email.strip().lower()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class EmailLoginResult:
    user: User
    created: bool
    next: str | None
    session_token: str  # for the cookie


class EmailLogins:
    def __init__(
        self,
        database: Database,
        mailer: Mailer,
        sessions: Sessions,
        *,
        base_url: str,
        clock: Clock = _now,
    ) -> None:
        self._database, self._mailer, self._sessions = database, mailer, sessions
        self._base_url = base_url.rstrip("/")
        self._clock = clock

    async def request(self, email: str, next: str | None, locale: str = "ru") -> Letter:
        """Store a new login link of the address; returns its letter for `send`."""
        token = secrets.token_urlsafe(32)
        now = self._clock()
        email = normalize(email)
        async with self._database.sessions.begin() as session:
            session.add(
                EmailToken(
                    token_hash=_hash(token),
                    email=email,
                    purpose="login",
                    next=next,
                    created_at=now,
                    expires_at=now + LINK_TTL,
                )
            )
        subject, body = LOGIN_LETTER[locale]
        link = LINK.format(base=self._base_url, token=token)
        minutes = int(LINK_TTL.total_seconds()) // 60
        return Letter("login-link", email, subject, body.format(link=link, minutes=minutes))

    async def send(self, letter: Letter) -> None:
        await self._mailer.send(letter)

    async def verify(self, token: str, user_agent: str | None) -> EmailLoginResult | None:
        """Spend a link and start a session of its user, creating the account at the first login;
        None when the token is unknown, used or expired."""
        if len(token) > TOKEN_MAX_LENGTH:
            return None
        now = self._clock()
        async with self._database.sessions.begin() as session:
            used = await session.execute(
                update(EmailToken)
                .where(
                    EmailToken.token_hash == _hash(token),
                    EmailToken.purpose == "login",
                    EmailToken.used_at.is_(None),
                    EmailToken.expires_at > now,
                )
                .values(used_at=now)
                .returning(EmailToken.email, EmailToken.next)
            )
            link = used.first()
            if link is None:
                return None
            email, next = link
            user, created = await sign_up(session, PROVIDER, email, email=email)
            session_token = await self._sessions.start(session, user.id, user_agent)
        return EmailLoginResult(user, created, next, session_token)
