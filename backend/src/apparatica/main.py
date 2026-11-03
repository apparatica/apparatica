"""The FastAPI application: `apparatica serve` or `uvicorn --factory apparatica.main:create_app`."""

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version
from typing import Any

import httpx2
import redis.asyncio
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import SecretStr

from apparatica.auth import api as auth_api
from apparatica.auth.csrf import CsrfMiddleware
from apparatica.auth.email_login import EmailLogins
from apparatica.auth.guests import GuestCookies
from apparatica.auth.oauth import Adapter, GitHub, OAuthLogins
from apparatica.auth.sessions import Sessions
from apparatica.captcha import api as captcha_api
from apparatica.captcha.altcha import Altcha
from apparatica.captcha.service import Captcha
from apparatica.core import api as core_api
from apparatica.core.api import AuthProvider
from apparatica.core.db import Database
from apparatica.core.errors import (
    ERROR_COMPONENT,
    ErrorCode,
    Problem,
    install_error_handlers,
    problem_responses,
)
from apparatica.core.flags import FeatureFlags, Overrides, database_overrides
from apparatica.core.logging import configure_logging
from apparatica.core.mail import Mailer, SmtpMailer
from apparatica.core.metrics import METRICS_PATH, metrics_endpoint
from apparatica.core.platform import load_platform_config
from apparatica.core.ratelimit import CACHE_TIMEOUT_S, ClientAddresses, RateLimiter
from apparatica.core.requests import RequestContextMiddleware
from apparatica.core.settings import Settings, get_settings
from apparatica.core.storage import Storage
from apparatica.problems import api as problems_api
from apparatica.submissions import api as submissions_api
from apparatica.submissions.queue import DramatiqQueue, JobQueue, NoQueue
from apparatica.submissions.quotas import Quotas
from apparatica.submissions.streams import StreamHub
from apparatica.submissions.tokens import JobTokens
from apparatica.users import api as users_api

API_PREFIX = "/api/v1"
VERSION = version("apparatica-backend")


def create_app(
    settings: Settings | None = None,
    flag_overrides: Overrides | None = None,
    job_queue: JobQueue | None = None,
    mailer: Mailer | None = None,
    oauth_transport: httpx2.AsyncBaseTransport | None = None,
) -> FastAPI:
    """`flag_overrides` replaces the `feature_flags` table as the source of flag overrides,
    `job_queue` the queue of checks (by default from APX_QUEUE_URL), `mailer` the SMTP server of
    APX_SMTP_URL, `oauth_transport` the network of the requests to the OAuth providers."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)
    platform = load_platform_config(settings.config_dir)  # fail fast on a broken config
    job_tokens = JobTokens(
        _secret(settings, settings.job_token_key, "APX_JOB_TOKEN_KEY"),
        ttl_s=settings.job_token_ttl_s,
    )
    guest_cookies = GuestCookies(
        _secret(settings, settings.guest_cookie_key, "APX_GUEST_COOKIE_KEY"),
        secure=settings.cookie_secure,
    )
    addresses = ClientAddresses(_secret(settings, settings.ip_hash_salt, "APX_IP_HASH_SALT"))
    captcha_rules = platform.rate_limits.captcha
    altcha = Altcha(
        _secret(settings, settings.captcha_key, "APX_CAPTCHA_KEY"),
        max_number=captcha_rules.max_number,
        expires_s=captcha_rules.expires_s,
    )
    database = Database(settings.database_url)  # connects on first use
    queue = job_queue or _job_queue(settings)  # connects on first use
    if settings.cache_url is None and settings.environment == "production":
        raise RuntimeError("APX_CACHE_URL is required in production")
    limiter = RateLimiter.connect(settings.cache_url)  # connects on first use
    cache = (
        redis.asyncio.Redis.from_url(
            settings.cache_url,
            socket_connect_timeout=CACHE_TIMEOUT_S,
            socket_timeout=CACHE_TIMEOUT_S,
        )
        if settings.cache_url is not None
        else None
    )
    sessions = Sessions(
        database, cache, ttl_s=settings.session_ttl_s, secure=settings.cookie_secure
    )
    email_logins = _email_logins(settings, database, sessions, mailer)
    oauth_logins = _oauth_logins(settings, database, sessions, oauth_transport)
    # One reader of the submission streams for the process (specs/07 §4.2); none without Valkey.
    hub = (
        StreamHub(redis.asyncio.Redis.from_url(settings.queue_url))
        if settings.queue_url is not None
        else None
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if hub is not None:
                await hub.close()
            if cache is not None:
                await cache.aclose()
            await queue.close()
            await database.dispose()

    app = FastAPI(
        title="Apparatica API",
        version=VERSION,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
        # operationId is the name of the handler: names in the TS client, e.g. list_problems.
        generate_unique_id_function=lambda route: route.name,
    )
    app.state.settings = settings
    app.state.version = VERSION
    app.state.platform = platform
    app.state.database = database
    app.state.flags = FeatureFlags(
        flag_overrides or database_overrides(database), ttl_s=settings.feature_flags_ttl_s
    )
    app.state.job_tokens = job_tokens
    app.state.stream_hub = hub
    app.state.storage = Storage(settings)  # event journals, pictures of statements
    app.state.job_queue = queue
    app.state.guest_cookies = guest_cookies
    app.state.sessions = sessions
    app.state.email_logins = email_logins
    app.state.oauth_logins = oauth_logins
    app.state.auth_providers = _auth_providers(oauth_logins, email_logins)
    app.state.client_addresses = addresses
    app.state.rate_limiter = limiter
    app.state.quotas = Quotas(platform.limits.quotas.guest, limiter, platform.rate_limits)
    app.state.captcha = Captcha(altcha, limiter, captcha_rules, app.state.flags)
    install_error_handlers(app)
    app.add_middleware(CsrfMiddleware, secure=settings.cookie_secure)
    app.add_middleware(RequestContextMiddleware)  # the outer one: CSRF_FAILED has a request id
    # Every operation may fail with INTERNAL; the routes declare their other errors.
    common = problem_responses(ErrorCode.INTERNAL)
    modules = (core_api, problems_api, submissions_api, captcha_api, auth_api, users_api)
    for module in modules:
        app.include_router(module.router, prefix=API_PREFIX, responses=common)
    # For Prometheus in the internal network, not part of the API (docs/configuration.md#метрики).
    app.add_api_route(METRICS_PATH, metrics_endpoint, include_in_schema=False)

    def openapi() -> dict[str, Any]:
        """The generated schema plus the error component that error responses refer to."""
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
            components = schema.setdefault("components", {}).setdefault("schemas", {})
            error = Problem.model_json_schema(ref_template="#/components/schemas/{model}")
            components.update(error.pop("$defs", {}))
            components[ERROR_COMPONENT] = error
            _event_stream_schemas(schema)
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
    return app


def _event_stream_schemas(schema: dict[str, Any]) -> None:
    """FastAPI types a response class other than JSON as a string and merges the declared model
    into it (`{"type": "string", "$ref": ...}`): the events of a stream are the model alone."""
    for item in schema["paths"].values():
        for operation in item.values():
            for response in operation["responses"].values():
                stream = response.get("content", {}).get("text/event-stream", {}).get("schema", {})
                if "$ref" in stream:
                    stream.pop("type", None)


def _email_logins(
    settings: Settings, database: Database, sessions: Sessions, mailer: Mailer | None
) -> EmailLogins | None:
    """Login links need a mail server and the address of the site for the link; none without."""
    if mailer is None and settings.smtp_url is not None:
        mailer = SmtpMailer(
            settings.smtp_url.get_secret_value(),
            settings.mail_from,
            timeout_s=settings.smtp_timeout_s,
        )
    if mailer is None:
        return None
    if settings.public_base_url is None:
        raise RuntimeError("APX_PUBLIC_BASE_URL is required with APX_SMTP_URL")
    return EmailLogins(database, mailer, sessions, base_url=settings.public_base_url)


def _oauth_logins(
    settings: Settings,
    database: Database,
    sessions: Sessions,
    transport: httpx2.AsyncBaseTransport | None,
) -> dict[str, OAuthLogins]:
    """The OAuth providers whose apps are configured, by key; the callback of an app is
    `<public_base_url>/api/v1/auth/<key>/callback`."""
    apps: list[tuple[Adapter, str | None, SecretStr | None]] = [
        (GitHub(), settings.github_client_id, settings.github_client_secret)
    ]
    logins = {}
    for adapter, client_id, client_secret in apps:
        name = f"APX_{adapter.key.upper()}"
        if client_id is None and client_secret is None:
            continue
        if client_id is None or client_secret is None:
            raise RuntimeError(f"{name}_CLIENT_ID and {name}_CLIENT_SECRET go together")
        if settings.public_base_url is None:
            raise RuntimeError(f"APX_PUBLIC_BASE_URL is required with {name}_CLIENT_ID")
        logins[adapter.key] = OAuthLogins(
            adapter,
            database,
            sessions,
            client_id=client_id,
            client_secret=client_secret.get_secret_value(),
            redirect_uri=f"{settings.public_base_url}{API_PREFIX}/auth/{adapter.key}/callback",
            timeout_s=settings.oauth_timeout_s,
            secure=settings.cookie_secure,
            transport=transport,
        )
    return logins


def _auth_providers(
    oauth_logins: dict[str, OAuthLogins], email_logins: EmailLogins | None
) -> list[AuthProvider]:
    """The configured ways to sign in, in the order of the login page: providers, then email."""
    providers = [
        AuthProvider(key=key, title=logins.adapter.title, kind="oauth")
        for key, logins in oauth_logins.items()
    ]
    if email_logins is not None:
        providers.append(AuthProvider(key="email", title="Email", kind="email"))
    return providers


def _job_queue(settings: Settings) -> JobQueue:
    if settings.queue_url is not None:
        return DramatiqQueue(settings.queue_url)
    if settings.environment == "production":
        raise RuntimeError("APX_QUEUE_URL is required in production")
    return NoQueue()


def _secret(settings: Settings, value: SecretStr | None, name: str) -> bytes:
    """A key of the settings; outside production an unset key is random, valid in this process
    only: the ingestor accepts no job tokens of it, and guests are forgotten on restart."""
    if value is not None:
        return value.get_secret_value().encode()
    if settings.environment == "production":
        raise RuntimeError(f"{name} is required in production")
    return secrets.token_bytes(32)
