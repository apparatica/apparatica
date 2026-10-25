import logging
import re
from collections.abc import Iterator

import pytest
from fastapi import APIRouter, Query
from fastapi.testclient import TestClient

from apparatica.core.errors import ApiError, ErrorCode
from apparatica.core.settings import Settings
from apparatica.main import create_app

PROBLEM = "application/problem+json"


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    router = APIRouter()

    @router.get("/limited")
    async def limited() -> None:
        raise ApiError(
            ErrorCode.RATE_LIMITED,
            "Guest limit is 10 checks per hour",
            params={"limit": 10, "retry_after_s": 761},
        )

    @router.get("/broken")
    async def broken() -> None:
        raise RuntimeError("boom")

    @router.get("/typed")
    async def typed(page: int = Query(ge=1)) -> dict[str, int]:
        return {"page": page}

    app.include_router(router, prefix="/api/v1/test")
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_api_error(client: TestClient) -> None:
    response = client.get("/api/v1/test/limited")
    assert response.status_code == 429
    assert response.headers["content-type"] == PROBLEM
    body = response.json()
    assert body == {
        "type": "https://apparatica.app/errors/rate-limited",
        "title": "Too Many Requests",
        "status": 429,
        "code": "RATE_LIMITED",
        "detail": "Guest limit is 10 checks per hour",
        "params": {"limit": 10, "retry_after_s": 761},
        "request_id": response.headers["x-request-id"],
    }


def test_unknown_route(client: TestClient) -> None:
    response = client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["code"] == "NOT_FOUND"


def test_wrong_method(client: TestClient) -> None:
    response = client.post("/api/v1/config")
    assert (response.status_code, response.json()["code"]) == (405, "METHOD_NOT_ALLOWED")


def test_validation_error(client: TestClient) -> None:
    response = client.get("/api/v1/test/typed", params={"page": 0})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["errors"] == [
        {
            "loc": ["query", "page"],
            "msg": "Input should be greater than or equal to 1",
            "type": "greater_than_equal",
        }
    ]


def test_unhandled_error_keeps_the_request_id(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        response = client.get("/api/v1/test/broken", headers={"X-Request-ID": "req-from-proxy-1"})
    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM
    assert response.headers["x-request-id"] == "req-from-proxy-1"
    body = response.json()
    assert (body["code"], body["request_id"]) == ("INTERNAL", "req-from-proxy-1")
    assert "boom" not in response.text  # no internals in the response


def test_request_id_is_generated_or_kept(client: TestClient) -> None:
    generated = client.get("/api/v1/health").headers["x-request-id"]
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", generated
    )
    kept = client.get("/api/v1/health", headers={"X-Request-ID": "abcdef12"})
    assert kept.headers["x-request-id"] == "abcdef12"
    replaced = client.get("/api/v1/health", headers={"X-Request-ID": "bad id\twith spaces"})
    assert replaced.headers["x-request-id"] != "bad id\twith spaces"
