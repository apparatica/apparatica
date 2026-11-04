"""Routes of the phase 2 contract validate their parameters (specs/05 §0)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/v1/auth/vk/login", None),  # phase 4
        ("GET", "/api/v1/auth/github/login?next=//evil.example", None),
        ("GET", "/api/v1/auth/github/login?next=/%5Cevil.example", None),
        ("GET", "/api/v1/auth/github/login?next=https://evil.example", None),
        ("POST", "/api/v1/auth/email/request", {"email": "not-an-address"}),
        ("POST", "/api/v1/auth/email/verify", {"token": "short"}),
        ("GET", "/api/v1/users/no%20such", None),
        ("GET", "/api/v1/problems?status=won", None),
        ("GET", "/api/v1/submissions?status=won", None),
    ],
)
def test_stubs_validate_parameters(client: TestClient, method: str, path: str, body: Any) -> None:
    response = client.request(method, path, json=body, follow_redirects=False)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
