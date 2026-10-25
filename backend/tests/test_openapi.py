"""The committed OpenAPI document (specs/05 §0, NFR-MAINT-01)."""

import json
from pathlib import Path
from typing import Any, get_args

from apparatica.cli import main, openapi_document
from apparatica.submissions.models import SUBMISSION_STATUSES
from apparatica.submissions.schemas import SubmissionStatus
from conftest import CONFIG_DIR

COMMITTED = Path(__file__).parents[1] / "openapi.json"


def test_committed_openapi_is_up_to_date() -> None:
    assert COMMITTED.read_text(encoding="utf-8") == openapi_document(CONFIG_DIR), (
        "backend/openapi.json is outdated: run `just openapi` and commit the result"
    )


def test_openapi_command_writes_the_document(tmp_path: Path) -> None:
    output = tmp_path / "openapi.json"
    assert main(["openapi", "--output", str(output), "--config-dir", str(CONFIG_DIR)]) == 0
    assert output.read_bytes() == openapi_document(CONFIG_DIR).encode()


def operations(schema: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (path, method, operation)
        for path, item in schema["paths"].items()
        for method, operation in item.items()
    ]


def test_errors_are_problem_json() -> None:
    schema = json.loads(openapi_document(CONFIG_DIR))
    assert "HTTPValidationError" not in schema["components"]["schemas"]
    assert "Error" in schema["components"]["schemas"]
    for path, method, operation in operations(schema):
        assert operation["x-phase"] == 0, (path, method)
        assert "500" in operation["responses"], (path, method)
        for status, response in operation["responses"].items():
            # A failed health check is a health report, not an error document.
            if int(status) >= 400 and (path, status) != ("/api/v1/health", "503"):
                assert list(response["content"]) == ["application/problem+json"], (path, status)
                assert response["content"]["application/problem+json"]["schema"] == {
                    "$ref": "#/components/schemas/Error"
                }


def test_submission_statuses_match_the_database_type() -> None:
    assert get_args(SubmissionStatus) == SUBMISSION_STATUSES
