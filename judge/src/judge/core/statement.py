"""The rendering check of statements (FR-PKG-03): an outside command, the renderer of the site.

The statements render on the site with KaTeX, WaveDrom and pictures from `assets/`
(`web/src/lib/statement`); the check runs that code, so the judge needs no Node.js of its own.
The command gets the package directory and the statement files:

    <command> <package-dir> <statement.md> [<statement.en.md> ...]

It prints one problem per line and exits with 0 (none), 1 (problems) or another code (it failed).
In the repository the command is `pnpm -C web --silent statement:check`.
"""

import shlex
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

TIMEOUT_S = 300.0


class StatementCheckError(Exception):
    """The command did not run or failed without a verdict."""


@dataclass(frozen=True)
class StatementCommand:
    argv: Sequence[str]
    timeout_s: float = TIMEOUT_S

    @classmethod
    def parse(cls, command: str) -> "StatementCommand":
        argv = shlex.split(command)
        if not argv:
            raise ValueError("an empty statement check command")
        return cls(argv)

    def __call__(self, package_dir: Path, names: Sequence[str]) -> list[str]:
        """The problems of the statements; empty when they render."""
        program, *rest = self.argv
        # On Windows a program such as pnpm is a .cmd file, which needs its full name.
        executable = shutil.which(program) or program
        try:
            completed = subprocess.run(
                [executable, *rest, str(package_dir.resolve()), *names],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_s,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise StatementCheckError(str(error)) from error
        lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        if completed.returncode == 0:
            return []
        if completed.returncode == 1 and lines:
            return lines
        output = completed.stderr.strip().splitlines() or lines
        raise StatementCheckError(
            f"exit code {completed.returncode}" + (f": {output[-1]}" if output else "")
        )
