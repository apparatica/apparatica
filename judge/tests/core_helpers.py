"""Fake stages and problems for the core tests: commands are Python one-liners on the host."""

import sys
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

import yaml
from pydantic import BaseModel, ConfigDict

from judge.core.events import Event
from judge.core.limits import ResourceClasses, load_resource_classes
from judge.core.package import Problem, parse_manifest
from judge.core.registry import LanguageModule
from judge.core.stage import (
    Command,
    ExecResult,
    StageContext,
    StageOutcome,
    StagePlan,
    StageSummary,
    TestCase,
)

ROOT = Path(__file__).parents[2]
RESOURCE_CLASSES: ResourceClasses = load_resource_classes(ROOT / "config" / "resource-classes.yaml")


def python(code: str) -> Command:
    return Command((sys.executable, "-c", code))


class ScriptConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    code: str = "pass"
    warn: bool = False


class ScriptStage:
    """Runs `code`; exit 0 passes, other exits fail as wrong; writes `out.txt` for later stages."""

    stage_type: ClassVar[str] = "script"
    config_model: ClassVar[type[BaseModel]] = ScriptConfig
    metrics_schema: ClassVar[str | None] = "script/v1"

    def plan(self, ctx: StageContext) -> StagePlan:
        assert isinstance(ctx.config, ScriptConfig)
        inputs = {name: f.outputs["out.txt"] for name, f in ctx.previous.items() if f.outputs}
        return StagePlan(
            commands=(python(ctx.config.code),),
            timeout_s=ctx.limits.timeout_s,
            output_limit=ctx.limits.output_bytes,
            inputs={"solution.sv": ctx.solution, **{f"from/{k}": v for k, v in inputs.items()}},
            collect=("out.txt",),
            line_filter=_progress,
        )

    def interpret(self, ctx: StageContext, runs: Sequence[ExecResult]) -> StageOutcome | StagePlan:
        assert isinstance(ctx.config, ScriptConfig)
        run = runs[-1]
        outputs = {"out.txt": run.files["out.txt"]} if "out.txt" in run.files else {}
        if run.timed_out:
            return StageOutcome(status="failed", failure_kind="limit", limit="time")
        if run.output_limited:
            return StageOutcome(status="failed", failure_kind="limit", limit="output")
        if not run.ok:
            tests = [TestCase(id="t1", name="first", group="public", status="failed", cycle=7)]
            return StageOutcome(
                status="failed", failure_kind="wrong", summary=StageSummary(tests=tests)
            )
        if ctx.config.warn:
            return StageOutcome(status="warning", metrics={"runs": len(runs)}, outputs=outputs)
        return StageOutcome(status="passed", metrics={"runs": len(runs)}, outputs=outputs)


def _progress(line: str) -> tuple[str | None, TestCase | None]:
    """`@@test <id>` lines become test progress and disappear from the console."""
    if line.startswith("@@test "):
        return None, TestCase(id=line[7:], name=line[7:], group="public", status="passed")
    return line, None


class RetryStage(ScriptStage):
    """Asks for a second run after a failed first one, like the trace window of `sim`."""

    stage_type: ClassVar[str] = "retry"

    def interpret(self, ctx: StageContext, runs: Sequence[ExecResult]) -> StageOutcome | StagePlan:
        if len(runs) == 1 and not runs[0].ok:
            # The second run sees what the first one left in the stage directory.
            again = python("print(open('left.txt').read())")
            return StagePlan(commands=(again,), timeout_s=5, output_limit=1024)
        return StageOutcome(status="passed", metrics={"runs": len(runs)})


class LoopStage(ScriptStage):
    stage_type: ClassVar[str] = "loop"

    def interpret(self, ctx: StageContext, runs: Sequence[ExecResult]) -> StageOutcome | StagePlan:
        return self.plan(ctx)


class CrashStage(ScriptStage):
    stage_type: ClassVar[str] = "crash"

    def interpret(self, ctx: StageContext, runs: Sequence[ExecResult]) -> StageOutcome | StagePlan:
        raise RuntimeError("plugin bug")


class MissingProgramStage(ScriptStage):
    stage_type: ClassVar[str] = "missing"

    def plan(self, ctx: StageContext) -> StagePlan:
        return StagePlan(
            commands=(Command(("apx-no-such-program",)),), timeout_s=5, output_limit=99
        )


class ArtifactStage(ScriptStage):
    """Keeps out.txt for the user instead of passing it on, like the FST trace of `sim`."""

    stage_type: ClassVar[str] = "artifact"

    def interpret(self, ctx: StageContext, runs: Sequence[ExecResult]) -> StageOutcome | StagePlan:
        return StageOutcome(status="passed", artifacts=dict(runs[-1].files))


class CachedStage(ScriptStage):
    """Builds `built` once: a later run of the stage finds it in the build cache."""

    stage_type: ClassVar[str] = "cached"

    def plan(self, ctx: StageContext) -> StagePlan:
        hit = ctx.build_cache.get("built")
        return StagePlan(
            commands=(python("pass"),),
            timeout_s=5,
            output_limit=1024,
            note=None if hit is None else f"from the cache: {hit.decode()}",
        )

    def interpret(self, ctx: StageContext, runs: Sequence[ExecResult]) -> StageOutcome | StagePlan:
        cached = ctx.build_cache.get("built") is not None
        if not cached:
            ctx.build_cache.put("built", b"binary")
        return StageOutcome(status="passed", cached=cached)


class MemoryCache:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def get(self, key: str) -> bytes | None:
        return self.files.get(key)

    def put(self, key: str, data: bytes) -> None:
        self.files[key] = data


FAKE = LanguageModule(
    name="systemverilog",
    stages={
        s.stage_type: s
        for s in (
            ScriptStage,
            RetryStage,
            LoopStage,
            CrashStage,
            MissingProgramStage,
            ArtifactStage,
            CachedStage,
        )
    },
)


def make_problem(
    stages: dict[str, dict[str, object]],
    run: list[str],
    submit: list[str] | None = None,
    **extra: object,
) -> Problem:
    manifest = {
        "schema": 1,
        "id": "demo",
        "number": 1,
        "version": 1,
        "leaderboard_epoch": 1,
        "language": "systemverilog",
        "kind": "design",
        "title": "Demo",
        "difficulty": "easy",
        "tags": ["demo"],
        "resource_class": "light",
        "top": "demo",
        "interface": {"ports": [{"name": "a", "dir": "input", "width": "1"}]},
        "files": {"statement": "statement.md", "template": "template.sv"},
        "stages": stages,
        "pipelines": {"practice": {"run": run, "submit": submit or run}},
        **extra,
    }
    return parse_manifest(yaml.safe_dump(manifest), "problem.yaml")


class ListSink:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


def cancel_after(seconds: float) -> threading.Event:
    cancel = threading.Event()
    threading.Timer(seconds, cancel.set).start()
    return cancel
