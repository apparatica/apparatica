"""Write the demo problems of the frontend mocks from their packages (specs/05 §0, T1.13).

The mock API answers `GET /problems/{slug}` and `GET /problems/{slug}/versions/{version}` with
web/src/mocks/problem-versions.json: the current version of every package in problems/, as the
API shows it (`ProblemVersionDetail`). The acceptance rates come from the catalogue fixtures.

    poetry -C judge run python ../scripts/mock_problems.py [--check]

A backend test checks the file against the API schema and the packages
(backend/tests/test_mock_scenarios.py).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from judge.core.package import Problem, load_manifest

ROOT = Path(__file__).resolve().parents[1]
PROBLEMS = ROOT / "problems"
OUTPUT = ROOT / "web" / "src" / "mocks" / "problem-versions.json"
PUBLISHED_AT = "2026-10-01T00:00:00Z"


def _stages(manifest: Problem, keys: list[str]) -> list[dict[str, str]]:
    return [{"key": key, "type": manifest.stages[key].type} for key in keys]


def _tests(manifest: Problem) -> dict[str, int]:
    tests: dict[str, int] = {}
    for testbench in manifest.testbenches:
        for group, count in testbench.groups.items():
            tests[group] = tests.get(group, 0) + count
    return tests


def detail(path: Path) -> dict[str, Any]:
    """The current version of a package as `GET /problems/{slug}/versions/{version}` shows it."""
    manifest = load_manifest(path)
    practice = manifest.pipelines.practice
    return {
        "slug": manifest.id,
        "number": manifest.number,
        "version": manifest.version,
        "current_version": manifest.version,
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
        "changelog": manifest.changelog,
        "published_at": PUBLISHED_AT,
    }


def build() -> str:
    packages = sorted(path.parent for path in PROBLEMS.glob("*/problem.yaml"))
    problems = sorted((detail(path) for path in packages), key=lambda problem: problem["number"])
    return json.dumps(problems, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the file is not current")
    args = parser.parse_args()
    text = build()
    if args.check:
        if OUTPUT.read_text(encoding="utf-8") != text:
            print(f"{OUTPUT.relative_to(ROOT)} is stale: run `just mock-problems`", file=sys.stderr)
            return 1
        return 0
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
