"""The data of the frontend mocks match the API: the recorded scenarios
(scripts/record_scenarios.py), the demo problems and their reference solutions
(scripts/mock_problems.py)."""

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from apparatica.leaderboards.schemas import ReferenceSolution
from apparatica.problems.schemas import ProblemVersionDetail
from apparatica.problems.service import _leaderboard, _pipeline, _reference, _tests
from apparatica.submissions.events import FinalizedEvent, QueueEvent, SubmissionEvent
from apparatica.submissions.schemas import Submission
from judge.core.package import load_manifest

ROOT = Path(__file__).parents[2]
SCENARIOS = ROOT / "web" / "src" / "mocks" / "scenarios"
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


def test_the_demo_problems_are_current() -> None:
    spec = importlib.util.spec_from_file_location(
        "mock_problems", ROOT / "scripts" / "mock_problems.py"
    )
    assert spec is not None
    assert spec.loader is not None
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    files: dict[Path, str] = script.build()
    assert sorted(files) == sorted([script.OUTPUT, script.REFERENCES])
    for path, text in files.items():
        assert path.read_text(encoding="utf-8") == text, "run `just mock-problems`"

    problems: list[dict[str, Any]] = json.loads(files[script.OUTPUT])
    references: dict[str, list[dict[str, Any]]] = json.loads(files[script.REFERENCES])
    assert sorted(references) == sorted(problem["slug"] for problem in problems)
    assert [problem["slug"] for problem in problems] == [
        "mux4",
        "counter-mod-n",
        "carry-adder",
        "seq-detector",
        "sync-fifo",
    ]
    for problem in problems:
        ProblemVersionDetail.model_validate(problem)
        # The script counts the stages and tests as the API does.
        manifest = load_manifest(ROOT / "problems" / problem["slug"])
        dumped = manifest.model_dump(mode="json", by_alias=True)
        assert problem["pipeline"] == _pipeline(dumped).model_dump()
        assert problem["tests"] == _tests(dumped)
        formula, reference = _leaderboard(dumped), _reference(dumped)
        assert problem["leaderboard"] == (formula and formula.model_dump(mode="json"))
        assert problem["reference"] == (reference and reference.model_dump())
        for solution in references[problem["slug"]]:
            ReferenceSolution.model_validate(solution | {"metrics": None})
