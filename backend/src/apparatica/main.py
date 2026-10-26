"""The FastAPI application: `apparatica serve` or `uvicorn --factory apparatica.main:create_app`."""

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from apparatica.captcha import api as captcha_api
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
from apparatica.core.requests import RequestContextMiddleware
from apparatica.core.settings import Settings, get_settings
from apparatica.problems import api as problems_api
from apparatica.submissions import api as submissions_api
from apparatica.submissions.queue import DramatiqQueue, JobQueue, NoQueue
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
    job_tokens = JobTokens(_job_token_key(settings), ttl_s=settings.job_token_ttl_s)
    database = Database(settings.database_url)  # connects on first use
    queue = job_queue or _job_queue(settings)  # connects on first use

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
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
    app.state.job_queue = queue
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


def _job_token_key(settings: Settings) -> bytes:
    if settings.job_token_key is not None:
        return settings.job_token_key.get_secret_value().encode()
    if settings.environment == "production":
        raise RuntimeError("APX_JOB_TOKEN_KEY is required in production")
    # Tokens of this process only: the ingestor needs the same key, so it accepts no results.
    return secrets.token_bytes(32)
