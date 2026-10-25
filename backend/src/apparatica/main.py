"""The FastAPI application: `apparatica serve` or `uvicorn --factory apparatica.main:create_app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from apparatica.core import api as core_api
from apparatica.core.db import Database
from apparatica.core.errors import Problem, install_error_handlers
from apparatica.core.flags import FeatureFlags, Overrides, database_overrides
from apparatica.core.logging import configure_logging
from apparatica.core.platform import load_platform_config
from apparatica.core.requests import RequestContextMiddleware
from apparatica.core.settings import Settings, get_settings

API_PREFIX = "/api/v1"
VERSION = version("apparatica-backend")


def create_app(
    settings: Settings | None = None, flag_overrides: Overrides | None = None
) -> FastAPI:
    """`flag_overrides` replaces the `feature_flags` table as the source of flag overrides."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)
    platform = load_platform_config(settings.config_dir)  # fail fast on a broken config
    database = Database(settings.database_url)  # connects on first use

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await database.dispose()

    app = FastAPI(
        title="Apparatica API",
        version=VERSION,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.version = VERSION
    app.state.platform = platform
    app.state.database = database
    app.state.flags = FeatureFlags(
        flag_overrides or database_overrides(database), ttl_s=settings.feature_flags_ttl_s
    )
    install_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(core_api.router, prefix=API_PREFIX)

    def openapi() -> dict[str, Any]:
        """The generated schema plus the Problem component that error responses refer to."""
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
            components = schema.setdefault("components", {}).setdefault("schemas", {})
            components["Problem"] = Problem.model_json_schema(
                ref_template="#/components/schemas/{model}"
            )
            components.update(components["Problem"].pop("$defs", {}))
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
    return app
