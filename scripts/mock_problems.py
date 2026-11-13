"""Write the demo problems of the frontend mocks from their packages (specs/05 §0, T1.13).

The mock API answers `GET /problems/{slug}` and `GET /problems/{slug}/versions/{version}` with
web/src/mocks/problem-versions.json: the current version of every package in problems/, as the
API shows it (`ProblemVersionDetail`). The acceptance rates come from the catalogue fixtures.
`GET /problems/{slug}/reference` shows the reference solutions of the packages,
web/src/mocks/reference-solutions.json (phase 3).

    poetry -C judge run python ../scripts/mock_problems.py [--check]

A backend test checks the file against the API schema and the packages
(backend/tests/test_mock_scenarios.py).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from judge.core.package import PRIMARY_SET, Problem, load_manifest, split_instance_key

ROOT = Path(__file__).resolve().parents[1]
PROBLEMS = ROOT / "problems"
OUTPUT = ROOT / "web" / "src" / "mocks" / "problem-versions.json"
REFERENCES = ROOT / "web" / "src" / "mocks" / "reference-solutions.json"
PUBLISHED_AT = "2026-10-01T00:00:00Z"


def _stages(manifest: Problem, keys: list[str]) -> list[dict[str, Any]]:
    """The stage instances, a stage at several parameter sets once per set (ADR-0014)."""
    stages = []
    for key in manifest.instance_keys(keys):
        stage_key, set_id = split_instance_key(key)
        param_set = None
        if manifest.stage_param_sets(stage_key) != [PRIMARY_SET]:
            values = manifest.interface.param_set_values(set_id)
            param_set = {"id": set_id, "values": values}
        stages.append({"key": key, "type": manifest.stages[stage_key].type, "param_set": param_set})
    return stages


def _tests(manifest: Problem) -> dict[str, int]:
    tests: dict[str, int] = {}
    for testbench in manifest.testbenches:
        for group, count in testbench.groups.items():
            tests[group] = tests.get(group, 0) + count
    return tests


def _reference(manifest: Problem) -> dict[str, Any] | None:
    reference = manifest.reference
    if reference is None or reference.visibility == "hidden" or not reference.solutions:
        return None
    return {
        "visibility": reference.visibility or "after_accepted",
        "solutions": len(reference.solutions),
    }


def detail(path: Path) -> dict[str, Any]:
    """The current version of a package as `GET /problems/{slug}/versions/{version}` shows it."""
    manifest = load_manifest(path)
    practice = manifest.pipelines.practice
    return {
        "slug": manifest.id,
        "number": manifest.number,
        "version": manifest.version,
        "title": manifest.title,
        "difficulty": manifest.difficulty,
        "tags": list(manifest.tags),
        "language": manifest.language,
        "resource_class": manifest.resource_class,
        "statement_md": (path / manifest.files.statement).read_text(encoding="utf-8"),
        "template": (path / manifest.files.template).read_text(encoding="utf-8"),
        "top": manifest.top,
        "interface": manifest.interface.model_dump(mode="json"),
        "pipeline": {
            "run": _stages(manifest, practice.run),
            "submit": _stages(manifest, practice.submit),
        },
        "tests": _tests(manifest),
        "leaderboard": (
            manifest.leaderboard.model_dump(mode="json") if manifest.leaderboard else None
        ),
        "reference": _reference(manifest),
        "changelog": manifest.changelog,
        "published_at": PUBLISHED_AT,
    }


def references(path: Path) -> list[dict[str, Any]]:
    """Reference solutions of a package as the importer stores them; the mocks add metrics."""
    manifest = load_manifest(path)
    solutions = manifest.reference.solutions if manifest.reference else []
    return [
        {
            "title": solution.title,
            "code": (path / solution.file).read_text(encoding="utf-8"),
            "explanation_md": (
                (path / solution.explanation).read_text(encoding="utf-8")
                if solution.explanation
                else None
            ),
        }
        for solution in solutions
    ]


def build() -> dict[Path, str]:
    packages = sorted(path.parent for path in PROBLEMS.glob("*/problem.yaml"))
    problems = sorted((detail(path) for path in packages), key=lambda problem: problem["number"])
    solutions = {path.name: references(path) for path in packages}
    return {
        OUTPUT: json.dumps(problems, ensure_ascii=False, indent=2) + "\n",
        REFERENCES: json.dumps(solutions, ensure_ascii=False, indent=2) + "\n",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the files are not current")
    args = parser.parse_args()
    files = build()
    if args.check:
        stale = [path for path, text in files.items() if path.read_text(encoding="utf-8") != text]
        for path in stale:
            print(f"{path.relative_to(ROOT)} is stale: run `just mock-problems`", file=sys.stderr)
        return 1 if stale else 0
    for path, text in files.items():
        path.write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
