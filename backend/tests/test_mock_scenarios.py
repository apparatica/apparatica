"""The recorded scenarios of the frontend mocks match the API (scripts/record_scenarios.py)."""

import json
from pathlib import Path
from typing import Any

import pytest

from apparatica.submissions.events import FinalizedEvent, QueueEvent, SubmissionEvent
from apparatica.submissions.schemas import Submission

SCENARIOS = Path(__file__).parents[2] / "web" / "src" / "mocks" / "scenarios"
FILES = sorted(SCENARIOS.glob("*.json"))


def test_there_are_scenarios() -> None:
    assert len(FILES) >= 10


@pytest.mark.parametrize("path", FILES, ids=[path.stem for path in FILES])
def test_a_scenario_matches_the_api(path: Path) -> None:
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    assert document["name"] == path.stem
    submission = Submission.model_validate(document["submission"])
    events = [SubmissionEvent.model_validate(item["event"]).root for item in document["events"]]

    ids = [tuple(int(part) for part in item["id"].split("-")) for item in document["events"]]
    assert ids == sorted(set(ids)), "stream ids grow"
    assert isinstance(events[0], QueueEvent)
    final = events[-1]
    assert isinstance(final, FinalizedEvent)
    assert [e for e in events if isinstance(e, FinalizedEvent)] == [final]
    assert (final.status, final.verdict_detail) == (submission.status, submission.verdict_detail)
    attempts = [e.attempt for e in events if hasattr(e, "attempt")]
    assert attempts == sorted(attempts)
    assert attempts[0] == 1
    has_trace = any(a.kind == "fst" for a in submission.artifacts)
    assert has_trace == ("fst" in document.get("files", {}))
