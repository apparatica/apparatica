"""The committed OpenAPI document (specs/05 §0, NFR-MAINT-01)."""

import json
from pathlib import Path
from typing import Any, get_args

from apparatica.cli import main, openapi_document
from apparatica.submissions import events
from apparatica.submissions.models import SUBMISSION_STATUSES
from apparatica.submissions.schemas import SubmissionStatus
from conftest import CONFIG_DIR
from judge.core import events as pipeline

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
        assert operation["x-phase"] in {0, 1}, (path, method)
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


def test_the_event_stream_is_typed() -> None:
    """specs/05 §0: the events are a component of the schema, so the TS client has their types."""
    schema = json.loads(openapi_document(CONFIG_DIR))
    stream = schema["paths"]["/api/v1/submissions/{id}/events"]["get"]["responses"]["200"]
    assert stream["content"] == {
        "text/event-stream": {"schema": {"$ref": "#/components/schemas/SubmissionEvent"}}
    }
    union = schema["components"]["schemas"]["SubmissionEvent"]
    for name in union["discriminator"]["mapping"].values():
        event = schema["components"]["schemas"][name.rsplit("/", 1)[1]]
        assert "type" in event["required"], name


def test_the_stream_has_every_pipeline_event() -> None:
    """The worker sends the pipeline events of the judge with the attempt number."""
    stream_events = get_args(events.SubmissionEvent.model_fields["root"].annotation)
    [union, _] = get_args(pipeline.Event.__value__)
    for event in get_args(union):
        [counterpart] = [e for e in stream_events if issubclass(e, event)]
        assert "attempt" in counterpart.model_fields, counterpart
