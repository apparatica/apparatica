"""Errors as RFC 9457 `application/problem+json` (specs/05 §2).

`code` is the stable machine code the frontend translates (messages/ru.json) with `params`;
`title` and `detail` are English, for developers. Raise `ApiError(ErrorCode.X, ...)` in handlers;
validation errors, unknown routes and unhandled exceptions get the same shape.
"""

from enum import StrEnum
from http import HTTPStatus
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_MEDIA_TYPE = "application/problem+json"
# The error schema in OpenAPI components: `Problem` would read as a problem of the catalogue.
ERROR_COMPONENT = "Error"
TYPE_BASE = "https://apparatica.app/errors/"

log = structlog.get_logger(__name__)


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    CSRF_FAILED = "CSRF_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    CAPTCHA_REQUIRED = "CAPTCHA_REQUIRED"
    CODE_TOO_LARGE = "CODE_TOO_LARGE"
    PROBLEM_VERSION_OUTDATED = "PROBLEM_VERSION_OUTDATED"
    HEAVY_NOT_ALLOWED = "HEAVY_NOT_ALLOWED"
    REFERENCE_LOCKED = "REFERENCE_LOCKED"
    SOLUTION_LOCKED = "SOLUTION_LOCKED"
    SUBMISSION_FINISHED = "SUBMISSION_FINISHED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    JUDGE_UNAVAILABLE = "JUDGE_UNAVAILABLE"
    INTERNAL = "INTERNAL"


STATUS: dict[ErrorCode, HTTPStatus] = {
    ErrorCode.VALIDATION_ERROR: HTTPStatus.UNPROCESSABLE_CONTENT,
    ErrorCode.NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.METHOD_NOT_ALLOWED: HTTPStatus.METHOD_NOT_ALLOWED,
    ErrorCode.UNAUTHENTICATED: HTTPStatus.UNAUTHORIZED,
    ErrorCode.FORBIDDEN: HTTPStatus.FORBIDDEN,
    ErrorCode.CSRF_FAILED: HTTPStatus.FORBIDDEN,
    ErrorCode.RATE_LIMITED: HTTPStatus.TOO_MANY_REQUESTS,
    ErrorCode.CAPTCHA_REQUIRED: HTTPStatus.PRECONDITION_REQUIRED,
    ErrorCode.CODE_TOO_LARGE: HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
    ErrorCode.PROBLEM_VERSION_OUTDATED: HTTPStatus.CONFLICT,
    ErrorCode.HEAVY_NOT_ALLOWED: HTTPStatus.FORBIDDEN,
    ErrorCode.REFERENCE_LOCKED: HTTPStatus.FORBIDDEN,
    ErrorCode.SOLUTION_LOCKED: HTTPStatus.FORBIDDEN,
    ErrorCode.SUBMISSION_FINISHED: HTTPStatus.CONFLICT,
    ErrorCode.NOT_IMPLEMENTED: HTTPStatus.NOT_IMPLEMENTED,
    ErrorCode.JUDGE_UNAVAILABLE: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCode.INTERNAL: HTTPStatus.INTERNAL_SERVER_ERROR,
}
# HTTP errors raised by the framework itself (unknown route, wrong method, ...).
_BY_STATUS = {
    HTTPStatus.NOT_FOUND: ErrorCode.NOT_FOUND,
    HTTPStatus.METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
    HTTPStatus.UNAUTHORIZED: ErrorCode.UNAUTHENTICATED,
    HTTPStatus.FORBIDDEN: ErrorCode.FORBIDDEN,
}


class FieldError(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class Problem(BaseModel):
    """An error response (`application/problem+json`)."""

    model_config = ConfigDict(json_schema_extra={"title": ERROR_COMPONENT})

    type: str = Field(examples=["https://apparatica.app/errors/rate-limited"])
    title: str
    status: int
    code: ErrorCode
    detail: str | None = None
    params: dict[str, Any] | None = None
    request_id: str | None = None
    errors: list[FieldError] | None = Field(default=None, description="With VALIDATION_ERROR")


class ApiError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        detail: str | None = None,
        *,
        params: dict[str, Any] | None = None,
        title: str | None = None,
    ) -> None:
        super().__init__(detail or code)
        self.code, self.detail, self.params, self.title = code, detail, params, title


def problem_response(
    request: Request,
    code: ErrorCode,
    *,
    detail: str | None = None,
    params: dict[str, Any] | None = None,
    title: str | None = None,
    errors: list[FieldError] | None = None,
) -> JSONResponse:
    status = STATUS[code]
    request_id = getattr(request.state, "request_id", None)
    body = Problem(
        type=TYPE_BASE + code.lower().replace("_", "-"),
        title=title or status.phrase,
        status=status,
        code=code,
        detail=detail,
        params=params,
        request_id=request_id,
        errors=errors,
    )
    headers = {"X-Request-ID": request_id} if request_id else None
    return JSONResponse(
        body.model_dump(mode="json", exclude_none=True),
        status_code=status,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


def problem_responses(*codes: ErrorCode) -> dict[int | str, dict[str, Any]]:
    """`responses=` for a route: these errors as problem+json in the OpenAPI schema."""
    schema = {"$ref": f"#/components/schemas/{ERROR_COMPONENT}"}  # added by create_app
    return {
        int(STATUS[code]): {
            "description": STATUS[code].phrase,
            "content": {PROBLEM_MEDIA_TYPE: {"schema": schema}},
        }
        for code in codes
    }


async def _api_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, ApiError)
    return problem_response(
        request, error.code, detail=error.detail, params=error.params, title=error.title
    )


async def _http_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, StarletteHTTPException)
    code = _BY_STATUS.get(HTTPStatus(error.status_code), ErrorCode.INTERNAL)
    detail = error.detail if isinstance(error.detail, str) else None
    return problem_response(request, code, detail=detail)


async def _validation_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RequestValidationError)
    errors = [FieldError(loc=list(e["loc"]), msg=e["msg"], type=e["type"]) for e in error.errors()]
    return problem_response(
        request, ErrorCode.VALIDATION_ERROR, detail="Invalid request parameters", errors=errors
    )


async def _unhandled(request: Request, error: Exception) -> JSONResponse:
    log.exception("unhandled error", path=request.url.path)
    return problem_response(request, ErrorCode.INTERNAL, detail="Unexpected server error")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled)
