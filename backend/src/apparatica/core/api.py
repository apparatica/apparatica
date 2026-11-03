"""`GET /health` and `GET /config` (specs/05 §3, phase 0)."""

import asyncio
from datetime import date
from typing import Literal

import structlog
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from apparatica.core.http import PRIVATE, cached_json
from apparatica.core.platform import Catalog, Difficulty, Limits, Operator

router = APIRouter(tags=["core"])
log = structlog.get_logger(__name__)

PHASE_0 = {"x-phase": 0}
CheckStatus = Literal["ok", "unavailable"]


class HealthResponse(BaseModel):
    status: CheckStatus
    version: str
    checks: dict[str, CheckStatus]


class AuthProvider(BaseModel):
    """An enabled way to sign in; the login page shows them in this order (FR-AUTH-01)."""

    key: str = Field(examples=["github", "email"])
    title: str = Field(examples=["GitHub"])
    kind: Literal["oauth", "email"] = Field(
        description="oauth: navigate to /auth/{key}/login; email: POST /auth/email/request"
    )


class LegalVersions(BaseModel):
    terms: date
    privacy: date


class LegalInfo(BaseModel):
    """The legal documents (FR-AUTH-06): the site renders their texts, the operator filled in."""

    draft: bool = Field(description="The texts await a lawyer; the site marks them as drafts")
    operator: Operator
    versions: LegalVersions = Field(description="The current editions, which a first login accepts")


class ConfigResponse(BaseModel):
    """What the frontend needs before anything else: features, levels, limits, login options,
    the legal documents."""

    version: str
    features: dict[str, bool]
    difficulties: list[Difficulty]
    catalog: Catalog
    limits: Limits
    auth_providers: list[AuthProvider]
    legal: LegalInfo


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "A dependency is unavailable"}},
    openapi_extra=PHASE_0,
)
async def health(request: Request, response: Response) -> HealthResponse:
    state = request.app.state
    checks: dict[str, CheckStatus] = {}
    try:
        async with asyncio.timeout(state.settings.health_timeout_s):
            await state.database.ping()
        checks["database"] = "ok"
    except Exception as error:  # any failure means "not ready"; the reason goes to the log
        log.warning("database health check failed", error=repr(error))
        checks["database"] = "unavailable"
    ok = all(value == "ok" for value in checks.values())
    response.status_code = 200 if ok else 503
    response.headers["Cache-Control"] = PRIVATE
    return HealthResponse(
        status="ok" if ok else "unavailable", version=state.version, checks=checks
    )


@router.get(
    "/config",
    response_model=ConfigResponse,
    openapi_extra=PHASE_0,
)
async def config(request: Request) -> Response:
    state = request.app.state
    features = await state.flags.values()
    # The configured providers (main.py); the flag `auth_<key>` turns one off.
    providers: list[AuthProvider] = state.auth_providers
    legal = state.platform.legal
    body = ConfigResponse(
        version=state.version,
        features=features,
        difficulties=state.platform.difficulties,
        catalog=state.platform.catalog,
        limits=state.platform.limits,
        auth_providers=[p for p in providers if features.get(f"auth_{p.key}", True)],
        legal=LegalInfo(
            draft=legal.draft,
            operator=legal.operator,
            versions=LegalVersions.model_validate(legal.documents.versions()),
        ),
    )
    return cached_json(request, body)
