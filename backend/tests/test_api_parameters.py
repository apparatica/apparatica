"""Parameters of the phase 1 routes are validated before the guest and the database."""

import pytest
from fastapi.testclient import TestClient

ID = "0192d1a2-7c00-7000-8000-000000000001"


@pytest.mark.parametrize(
    ("path", "headers"),
    [
        (f"/api/v1/submissions/{ID}/events?from=latest", {}),
        (f"/api/v1/submissions/{ID}/events", {"Last-Event-ID": "x"}),
        (f"/api/v1/submissions/{ID}/artifacts/tb_result", {}),
        ("/api/v1/submissions?limit=101", {}),
    ],
)
def test_parameters_are_validated(client: TestClient, path: str, headers: dict[str, str]) -> None:
    response = client.get(path, headers=headers)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
