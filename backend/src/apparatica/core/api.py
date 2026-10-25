"""`GET /health` and `GET /config` (specs/05 §3, phase 0)."""

import asyncio
from typing import Literal

import structlog
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from apparatica.core.errors import ErrorCode, problem_responses
from apparatica.core.http import PRIVATE, cached_json
from apparatica.core.platform import Difficulty, Limits

router = APIRouter(tags=["core"])
log = structlog.get_logger(__name__)

PHASE_0 = {"x-phase": 0}
CheckStatus = Literal["ok", "unavailable"]


class HealthResponse(BaseModel):
    status: CheckStatus
    version: str
    checks: dict[str, CheckStatus]


class AuthProvider(BaseModel):
    key: str
    title: str


class ConfigResponse(BaseModel):
    """What the frontend needs before anything else: features, levels, limits, login options."""

    version: str
    features: dict[str, bool]
    difficulties: list[Difficulty]
    limits: Limits
    auth_providers: list[AuthProvider]


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
    responses=problem_responses(ErrorCode.INTERNAL),
    openapi_extra=PHASE_0,
)
async def config(request: Request) -> Response:
    state = request.app.state
    body = ConfigResponse(
        version=state.version,
        features=await state.flags.values(),
        difficulties=state.platform.difficulties,
        limits=state.platform.limits,
        auth_providers=[],  # login arrives in phase 2 (GitHub, email)
    )
    return cached_json(request, body)
