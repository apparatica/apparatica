"""Problem packages that CI must validate for a change (FR-PKG-05, specs/09 §4.1).

A change of a package validates that package. A change of anything that judges packages — the
judge, the toolchain image, the resource classes, the statement renderer, the workflow — validates
all of them: that is the regression of references, mutants and statements.

    python scripts/changed_problems.py <base-ref>   # changed files: git diff <base-ref>...HEAD
    python scripts/changed_problems.py --all

Prints package directories, one per line (nothing: no package to validate).
"""

import argparse
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

PROBLEMS = PurePosixPath("problems")
MANIFEST = "problem.yaml"
# Changes under these paths can change the verdict of any package.
REGRESSION_PATHS = (
    "judge/src/",
    "judge/poetry.lock",
    "toolchain/",
    "config/resource-classes.yaml",
    "web/src/lib/statement/",
    "web/scripts/statement-check.ts",
    ".github/workflows/problems.yml",
    "scripts/changed_problems.py",
)


def packages(root: Path) -> list[str]:
    """Package directories under problems/, as POSIX paths relative to the repository."""
    return sorted(
        (PROBLEMS / path.parent.name).as_posix() for path in (root / PROBLEMS).glob(f"*/{MANIFEST}")
    )


def select(changed: Iterable[str], existing: list[str]) -> list[str]:
    selected = set()
    for name in changed:
        if name.startswith(REGRESSION_PATHS):
            return existing
        parts = PurePosixPath(name).parts
        if len(parts) > 2 and parts[0] == PROBLEMS.name:
            package = (PROBLEMS / parts[1]).as_posix()
            if package in existing:  # a deleted package has nothing left to validate
                selected.add(package)
    return sorted(selected)


def _changed_files(base: str) -> list[str]:
    diff = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return diff.stdout.splitlines()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("base", nargs="?", help="base revision of the change")
    parser.add_argument("--all", action="store_true", help="every package")
    args = parser.parse_args(argv)
    if not args.all and not args.base:
        parser.error("pass a base revision or --all")
    root = Path.cwd()
    existing = packages(root)
    selected = existing if args.all else select(_changed_files(args.base), existing)
    for package in selected:
        print(package)
    return 0


if __name__ == "__main__":
    sys.exit(main())
