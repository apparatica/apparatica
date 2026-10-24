"""Fail if Poetry lock files of the Python projects pin shared packages to different versions.

`backend` and `worker` depend on `judge` by path, so every package present in more than one
lock file must resolve to the same version everywhere (ADR-0001).
"""

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ("judge", "backend", "worker")


def load_versions(project: str) -> dict[str, str]:
    lock = tomllib.loads((ROOT / project / "poetry.lock").read_text(encoding="utf-8"))
    return {
        package["name"]: package["version"]
        for package in lock.get("package", [])
        # Path dependencies (the projects themselves) are not pinned by version.
        if package.get("source", {}).get("type") != "directory"
    }


def main() -> int:
    versions = {project: load_versions(project) for project in PROJECTS}
    names = sorted({name for pinned in versions.values() for name in pinned})
    mismatches = []
    for name in names:
        pinned = {p: versions[p][name] for p in PROJECTS if name in versions[p]}
        if len(set(pinned.values())) > 1:
            details = ", ".join(f"{p}={v}" for p, v in pinned.items())
            mismatches.append(f"  {name}: {details}")

    if mismatches:
        print("Shared dependencies resolve to different versions:", file=sys.stderr)
        print("\n".join(mismatches), file=sys.stderr)
        print("Align constraints and run `poetry lock` in affected projects.", file=sys.stderr)
        return 1
    print(f"Lock files are consistent ({len(names)} packages across {', '.join(PROJECTS)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
