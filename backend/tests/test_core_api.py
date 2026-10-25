from collections.abc import Mapping

from fastapi.testclient import TestClient

from apparatica.core.settings import Settings
from apparatica.main import VERSION, create_app


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": VERSION, "checks": {"database": "ok"}}
    assert response.headers["cache-control"] == "private, no-store"


def test_health_without_database(settings: Settings) -> None:
    broken = settings.model_copy(
        update={
            "database_url": "postgresql+asyncpg://nobody@127.0.0.1:1/none",
            "health_timeout_s": 2,
        }
    )
    with TestClient(create_app(broken)) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "unavailable"}


def test_config(client: TestClient) -> None:
    response = client.get("/api/v1/config")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == VERSION
    assert body["features"] == {
        "captcha": False,
        "formal_stage": False,
        "industrial_mode": False,
        "reports": False,
    }
    assert [d["key"] for d in body["difficulties"]] == ["easy", "medium", "hard"]
    assert body["limits"]["solution"] == {"max_bytes": 65536, "max_lines": 2000}
    assert body["limits"]["quotas"]["guest"]["checks_per_hour"] == 10
    assert body["auth_providers"] == []
    assert response.headers["cache-control"] == "public, max-age=60, stale-while-revalidate=300"


def test_config_etag(client: TestClient) -> None:
    etag = client.get("/api/v1/config").headers["etag"]
    cached = client.get("/api/v1/config", headers={"If-None-Match": etag})
    assert cached.status_code == 304
    assert cached.content == b""
    assert cached.headers["etag"] == etag
    other = client.get("/api/v1/config", headers={"If-None-Match": '"other", W/' + etag})
    assert other.status_code == 304
    assert client.get("/api/v1/config", headers={"If-None-Match": '"x"'}).status_code == 200


def test_config_shows_flag_overrides(settings: Settings) -> None:
    async def overrides() -> Mapping[str, bool]:
        return {"captcha": True}

    with TestClient(create_app(settings, overrides)) as client:
        assert client.get("/api/v1/config").json()["features"]["captcha"] is True


def test_openapi(client: TestClient) -> None:
    schema = client.get("/api/v1/openapi.json").json()
    assert schema["components"]["schemas"]["Error"]["properties"]["code"]["$ref"] == (
        "#/components/schemas/ErrorCode"
    )
    assert "ErrorCode" in schema["components"]["schemas"]
    config = schema["paths"]["/api/v1/config"]["get"]
    assert config["x-phase"] == 0
    assert config["responses"]["500"]["content"] == {
        "application/problem+json": {"schema": {"$ref": "#/components/schemas/Error"}}
    }
