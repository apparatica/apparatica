"""Routes of the phase 2 contract answer 501 NOT_IMPLEMENTED until implemented (specs/05 §0)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

PROBLEM = "application/problem+json"


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("DELETE", "/api/v1/me", None),
        ("POST", "/api/v1/me/restore", None),
        ("GET", "/api/v1/me/export", None),
        ("GET", "/api/v1/me/drafts/mux4", None),
        ("PUT", "/api/v1/me/drafts/mux4", {"code": "module m; endmodule", "problem_version": 2}),
        ("GET", "/api/v1/users/ada", None),
        ("GET", "/api/v1/problems?status=solved", None),
        ("GET", "/api/v1/submissions?status=accepted", None),
    ],
)
def test_stubs_are_not_implemented(client: TestClient, method: str, path: str, body: Any) -> None:
    response = client.request(method, path, json=body, follow_redirects=False)
    assert response.status_code == 501
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["code"] == "NOT_IMPLEMENTED"


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/v1/auth/vk/login", None),  # phase 4
        ("GET", "/api/v1/auth/github/login?next=//evil.example", None),
        ("GET", "/api/v1/auth/github/login?next=/%5Cevil.example", None),
        ("GET", "/api/v1/auth/github/login?next=https://evil.example", None),
        ("POST", "/api/v1/auth/email/request", {"email": "not-an-address"}),
        ("POST", "/api/v1/auth/email/verify", {"token": "short"}),
        ("PUT", "/api/v1/me/drafts/mux4", {"code": "", "problem_version": 0}),
        ("GET", "/api/v1/users/no%20such", None),
        ("GET", "/api/v1/problems?status=won", None),
        ("GET", "/api/v1/submissions?status=won", None),
    ],
)
def test_stubs_validate_parameters(client: TestClient, method: str, path: str, body: Any) -> None:
    response = client.request(method, path, json=body, follow_redirects=False)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
