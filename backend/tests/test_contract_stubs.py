"""Routes of the phase 1 contract answer 501 NOT_IMPLEMENTED until implemented (specs/05 §0)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

PROBLEM = "application/problem+json"
ID = "0192d1a2-7c00-7000-8000-000000000001"


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/v1/submissions?problem=mux4", None),
        ("POST", f"/api/v1/submissions/{ID}/cancel", None),
        ("GET", f"/api/v1/submissions/{ID}/artifacts/fst?stage=sim_run", None),
        ("POST", f"/api/v1/submissions/{ID}/waveform", {"scope": "full_test", "test": "t7"}),
        ("GET", "/api/v1/captcha/challenge", None),
    ],
)
def test_stubs_are_not_implemented(client: TestClient, method: str, path: str, body: Any) -> None:
    response = client.request(method, path, json=body, follow_redirects=False)
    assert response.status_code == 501
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["code"] == "NOT_IMPLEMENTED"


@pytest.mark.parametrize(
    ("path", "headers"),
    [
        (f"/api/v1/submissions/{ID}/events?from=latest", {}),
        (f"/api/v1/submissions/{ID}/events", {"Last-Event-ID": "x"}),
        (f"/api/v1/submissions/{ID}/artifacts/tb_result", {}),
        ("/api/v1/submissions?limit=101", {}),
    ],
)
def test_stubs_validate_parameters(client: TestClient, path: str, headers: dict[str, str]) -> None:
    response = client.get(path, headers=headers)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
