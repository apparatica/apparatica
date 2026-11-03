"""Logins with OAuth providers (FR-AUTH-01, ADR-0010): GitHub in phase 2; VK ID, Yandex ID and
Google join in phase 4 as more adapters.

A login is two navigations of the browser. `/auth/{provider}/login` sends it to the authorization
page of the provider with a random `state` and a PKCE challenge (S256); the state, the verifier and
`next` go to the cookie `ap_oauth` of the callback path for 10 minutes. The provider returns the
browser to `/auth/{provider}/callback` with a code. The state of the query must be that of the
cookie: a callback that another browser started (login CSRF) or an old one fails. The code and the
verifier buy an access token, the token the profile of the user; the identity is the key of the
account (`accounts.sign_up`). The token is not kept.
"""

import base64
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Literal
from urllib.parse import urlsplit

import httpx2
import structlog
from authlib.common.errors import AuthlibBaseError
from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastapi import Response
from pydantic import BaseModel

from apparatica.auth.accounts import sign_up
from apparatica.auth.models import User
from apparatica.auth.schemas import NextPath
from apparatica.auth.sessions import Sessions
from apparatica.core.db import Database

log = structlog.get_logger(__name__)

COOKIE = "ap_oauth"
PENDING_TTL_S = 600  # from the start of a login to its callback
COOKIE_MAX_LENGTH = 4096
LoginFailure = Literal["access_denied", "invalid_state", "provider_error"]  # docs/api.md


@dataclass(frozen=True)
class OAuthProfile:
    """The user as the provider tells: the account at the provider and what a new account takes."""

    subject: str  # the stable id of the account at the provider, never a nick it lets change
    nick: str | None
    display_name: str | None
    avatar_url: str | None
    email: str | None


class Adapter(ABC):
    """A provider: its endpoints and how a token reads the profile. Logins of every provider are
    the same otherwise (`OAuthLogins`)."""

    key: ClassVar[str]  # of the routes, identities.provider and the flag auth_<key>
    title: ClassVar[str]
    authorize_url: ClassVar[str]
    token_url: ClassVar[str]
    scope: ClassVar[str | None]

    @abstractmethod
    async def profile(self, client: AsyncOAuth2Client) -> OAuthProfile:
        """Read the profile with the token of the client; raises on an unexpected answer."""


class _GitHubUser(BaseModel):
    """The fields of GET /user that a login reads (docs.github.com/rest/users/users)."""

    id: int
    login: str
    name: str | None = None
    avatar_url: str | None = None
    email: str | None = None  # the public address, if the user has one


class GitHub(Adapter):
    key = "github"
    title = "GitHub"
    authorize_url = "https://github.com/login/oauth/authorize"
    token_url = "https://github.com/login/oauth/access_token"
    # No scope: the token reads public data only, and the user is asked for nothing else.
    scope = None
    user_url = "https://api.github.com/user"

    async def profile(self, client: AsyncOAuth2Client) -> OAuthProfile:
        response = await client.get(
            self.user_url,
            headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
        )
        response.raise_for_status()
        user = _GitHubUser.model_validate_json(response.content)
        return OAuthProfile(str(user.id), user.login, user.name, user.avatar_url, user.email)


class _Pending(BaseModel):
    """A started login: the value of the cookie, base64 of its JSON."""

    provider: str
    state: str
    verifier: str
    next: NextPath | None


class LoginError(Exception):
    def __init__(self, reason: LoginFailure) -> None:
        super().__init__(reason)
        self.reason: LoginFailure = reason


@dataclass(frozen=True)
class OAuthLoginResult:
    user: User
    created: bool
    next: str | None
    session_token: str  # for the cookie


class OAuthLogins:
    """Logins with one provider through its OAuth app."""

    def __init__(
        self,
        adapter: Adapter,
        database: Database,
        sessions: Sessions,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        timeout_s: float,
        secure: bool,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self.adapter = adapter
        self._database, self._sessions = database, sessions
        self._client_id, self._client_secret = client_id, client_secret
        self._redirect_uri = redirect_uri
        self._cookie_path = urlsplit(redirect_uri).path  # the cookie goes to the callback only
        self._timeout_s, self._secure, self._transport = timeout_s, secure, transport

    def start(self, next: str | None) -> tuple[str, str]:
        """The authorization URL of a new login and the value of its cookie."""
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        url, _ = self._client().create_authorization_url(
            self.adapter.authorize_url, state=state, code_verifier=verifier
        )
        pending = _Pending(provider=self.adapter.key, state=state, verifier=verifier, next=next)
        return url, base64.urlsafe_b64encode(pending.model_dump_json().encode()).decode()

    async def finish(
        self,
        *,
        code: str | None,
        state: str | None,
        error: str | None,
        cookie: str | None,
        user_agent: str | None,
    ) -> OAuthLoginResult:
        """Sign in with the answer of the provider, creating the account at the first login;
        LoginError with the reason for the login page otherwise."""
        if error is not None:  # the user declined, or the app is misconfigured at the provider
            raise LoginError("access_denied" if error == "access_denied" else "provider_error")
        pending = _read(cookie)
        if (
            pending is None
            or pending.provider != self.adapter.key
            or state is None
            or not secrets.compare_digest(pending.state.encode(), state.encode())
        ):
            raise LoginError("invalid_state")
        if code is None:
            raise LoginError("provider_error")
        profile = await self._profile(code, pending.verifier)
        async with self._database.sessions.begin() as session:
            user, created = await sign_up(
                session,
                self.adapter.key,
                profile.subject,
                email=profile.email,
                nick=profile.nick,
                display_name=profile.display_name,
                avatar_url=profile.avatar_url,
            )
            session_token = await self._sessions.start(session, user.id, user_agent)
        return OAuthLoginResult(user, created, pending.next, session_token)

    def set_cookie(self, response: Response, value: str) -> None:
        response.set_cookie(
            COOKIE,
            value,
            max_age=PENDING_TTL_S,
            path=self._cookie_path,
            secure=self._secure,
            httponly=True,
            samesite="lax",  # the provider returns the browser with a top-level navigation
        )

    def clear_cookie(self, response: Response) -> None:
        response.delete_cookie(
            COOKIE, path=self._cookie_path, secure=self._secure, httponly=True, samesite="lax"
        )

    async def _profile(self, code: str, verifier: str) -> OAuthProfile:
        try:
            async with self._client() as client:
                await client.fetch_token(self.adapter.token_url, code=code, code_verifier=verifier)
                return await self.adapter.profile(client)
        except (httpx2.HTTPError, AuthlibBaseError, ValueError) as error:  # ValidationError too
            log.warning("oauth login failed", provider=self.adapter.key, error=str(error))
            raise LoginError("provider_error") from error

    def _client(self) -> Any:  # Authlib has no annotations
        return AsyncOAuth2Client(
            client_id=self._client_id,
            client_secret=self._client_secret,
            token_endpoint_auth_method="client_secret_post",
            scope=self.adapter.scope,
            redirect_uri=self._redirect_uri,
            code_challenge_method="S256",
            timeout=self._timeout_s,
            transport=self._transport,
        )


def _read(cookie: str | None) -> _Pending | None:
    if not cookie or len(cookie) > COOKIE_MAX_LENGTH:
        return None
    try:
        return _Pending.model_validate_json(base64.urlsafe_b64decode(cookie))
    except ValueError:  # binascii.Error and ValidationError are ValueErrors
        return None
