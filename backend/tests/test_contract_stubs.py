"""Routes of the phase 2 and 3 contracts validate their parameters (specs/05 §0)."""

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
        ("GET", "/api/v1/problems/Mux4/leaderboard", None),
        ("GET", "/api/v1/problems/mux4/leaderboard?around=you", None),
        ("GET", "/api/v1/problems/mux4/leaderboard?sort=delay", None),
        ("GET", "/api/v1/problems/mux4/leaderboard?per_page=101", None),
        ("GET", "/api/v1/problems/mux4/solutions?sort=--submitted_at", None),
        ("GET", "/api/v1/problems/mux4/solutions?page=0", None),
        ("GET", "/api/v1/solutions/2917", None),
        ("GET", "/api/v1/leaderboard?per_page=0", None),
        ("GET", "/api/v1/users/no%20such/solutions", None),
    ],
)
def test_stubs_validate_parameters(client: TestClient, method: str, path: str, body: Any) -> None:
    response = client.request(method, path, json=body, follow_redirects=False)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/users/ada/solutions",
    ],
)
def test_phase_3_stubs(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 501
    assert response.json()["code"] == "NOT_IMPLEMENTED"
