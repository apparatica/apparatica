"""Build cache (ADR-0003, specs/07 §2.3): files a stage built once, e.g. the simulation binary, kept
by a key of everything the build read. Run → Submit of the same code builds once.

The key of a stage is `plan_key` of its build plan: the commands and every input, so a change of
the build flags, the testbench or the design is a new key. Whoever provides the cache scopes the
keys with the toolchain (the worker: the profile and the image digest), which the plan does not
name. A cache failure is a miss, never a failed check.
"""

import hashlib
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:  # judge.core.stage imports this module
    from judge.core.stage import StagePlan


class BuildCache(Protocol):
    def get(self, key: str) -> bytes | None:
        """The file stored under the key, or None (missing, expired or unreadable)."""
        ...

    def put(self, key: str, data: bytes) -> None:
        """Keep the file; a failure is logged, not raised."""
        ...


class NoCache:
    """Every lookup misses: `judge` on a developer machine and in CI."""

    def get(self, key: str) -> bytes | None:
        return None

    def put(self, key: str, data: bytes) -> None:
        pass


NO_CACHE = NoCache()


def plan_key(stage_type: str, plan: "StagePlan") -> str:
    """sha256 of what a build plan reads: the stage type, the commands and the inputs."""
    digest = hashlib.sha256(f"{stage_type}\n".encode())
    for command in plan.commands:
        digest.update(b"cmd\0" + b"\0".join(arg.encode() for arg in command.argv) + b"\n")
    for name in sorted(plan.inputs):
        content = hashlib.sha256(plan.inputs[name]).hexdigest()
        executable = "x" if name in plan.executable else "-"
        digest.update(f"in\0{name}\0{executable}\0{content}\n".encode())
    return digest.hexdigest()
