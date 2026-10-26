"""The FastAPI application: `apparatica serve` or `uvicorn --factory apparatica.main:create_app`."""

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version
from typing import Any

import redis.asyncio
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import SecretStr

from apparatica.auth.guests import GuestCookies
from apparatica.captcha import api as captcha_api
from apparatica.captcha.altcha import Altcha
from apparatica.captcha.service import Captcha
from apparatica.core import api as core_api
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
from apparatica.core.platform import load_platform_config
from apparatica.core.ratelimit import ClientAddresses, RateLimiter
from apparatica.core.requests import RequestContextMiddleware
from apparatica.core.settings import Settings, get_settings
from apparatica.core.storage import Storage
from apparatica.problems import api as problems_api
from apparatica.submissions import api as submissions_api
from apparatica.submissions.queue import DramatiqQueue, JobQueue, NoQueue
from apparatica.submissions.quotas import Quotas
from apparatica.submissions.streams import StreamHub
from apparatica.submissions.tokens import JobTokens

API_PREFIX = "/api/v1"
VERSION = version("apparatica-backend")


def create_app(
    settings: Settings | None = None,
    flag_overrides: Overrides | None = None,
    job_queue: JobQueue | None = None,
) -> FastAPI:
    """`flag_overrides` replaces the `feature_flags` table as the source of flag overrides,
    `job_queue` the queue of checks (by default from APX_QUEUE_URL)."""
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
    app.state.storage = Storage(settings)  # the event journals of finished checks
    app.state.job_queue = queue
    app.state.guest_cookies = guest_cookies
    app.state.client_addresses = addresses
    app.state.rate_limiter = limiter
    app.state.quotas = Quotas(platform.limits.quotas.guest, limiter, platform.rate_limits)
    app.state.captcha = Captcha(altcha, limiter, captcha_rules, app.state.flags)
    install_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)
    # Every operation may fail with INTERNAL; the routes declare their other errors.
    common = problem_responses(ErrorCode.INTERNAL)
    for module in (core_api, problems_api, submissions_api, captcha_api):
        app.include_router(module.router, prefix=API_PREFIX, responses=common)

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
