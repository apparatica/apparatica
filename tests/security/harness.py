"""The sandbox of the security suite: the judge pipeline over apx-sandboxd, as a worker runs it."""

import os
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

from apparatica_worker.sandboxd.client import SandboxdClient, SandboxExecutor
from apparatica_worker.sandboxd.server import LABEL
from judge.core.events import Event, LogEvent
from judge.core.limits import load_resource_classes, sandbox_limits
from judge.core.package import load_manifest
from judge.core.pipeline import Job, run_pipeline
from judge.core.registry import get_language
from judge.core.stage import Command, ExecResult, StagePlan, StageResult, SubmissionKind
from judge.core.verdict import Verdict, aggregate

ROOT = Path(__file__).parents[2]
HERE = Path(__file__).parent
PACKAGE = HERE / "counter"
IMAGE = os.environ.get("TOOLCHAIN_IMAGE", "apparatica-toolchain:dev")
# runsc in CI and on the worker hosts (ADR-0003); runc where gVisor is not installed.
RUNTIME = os.environ.get("JUDGE_SANDBOX_RUNTIME", "runc")
CLASSES = load_resource_classes(ROOT / "config" / "resource-classes.yaml")
PROBLEM = load_manifest(PACKAGE)
LIMITS = sandbox_limits(PROBLEM, CLASSES)
SEED = 42

Lines = list[tuple[str, str]]


@dataclass
class Check:
    """One check of a solution: the stage results, the verdict and the events."""

    results: list[StageResult]
    events: list[Event] = field(default_factory=list)

    @property
    def verdict(self) -> Verdict:
        return aggregate(self.results)

    def emit(self, event: Event) -> None:
        self.events.append(event)

    def describe(self) -> str:
        """Stage results and the first lines of the console, for assertion messages."""
        stages = [
            f"{r.key}: {r.status} {r.failure_kind or ''} {r.limit or ''} {r.error_code or ''} "
            f"{[d.code for d in r.summary.diagnostics]}"
            for r in self.results
        ]
        logs = [f"{e.stage} {e.ch}: {e.text}" for e in self.events if isinstance(e, LogEvent)]
        return "\n".join([*stages, *logs[:20]])


def judge(
    client: SandboxdClient,
    solution: bytes,
    *,
    kind: SubmissionKind = "run",
    stages: tuple[str, ...] | None = None,
) -> Check:
    """Check a solution of the suite's counter problem in a sandbox of its own."""
    job = Job(PROBLEM, PACKAGE, kind, SEED, solution, stages)
    check = Check(results=[])
    with SandboxExecutor(client, IMAGE, LIMITS) as executor:
        check.results = run_pipeline(job, get_language("systemverilog"), executor, check, CLASSES)
    return check


def sh(script: str) -> Command:
    return Command(("sh", "-c", script))


def stage(
    executor: SandboxExecutor,
    key: str,
    *commands: Command,
    timeout_s: float = 30,
    output_limit: int = 1 << 16,
) -> tuple[ExecResult, Lines]:
    """Run commands as a stage would: what code that took over a tool can do in the sandbox."""
    lines: Lines = []
    plan = StagePlan(commands=commands, timeout_s=timeout_s, output_limit=output_limit)
    result = executor.run(
        key, plan, lambda channel, text: lines.append((channel, text)), threading.Event()
    )
    return result, lines


def text(lines: Lines) -> str:
    return "\n".join(line for _, line in lines)


def sandbox_containers() -> list[str]:
    """Containers of apx-sandboxd on the host, running or not."""
    listed = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"label={LABEL}", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return listed.stdout.split()
