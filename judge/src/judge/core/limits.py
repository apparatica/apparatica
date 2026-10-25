"""Sandbox and stage limits: resource class defaults (config/resource-classes.yaml, NFR-LIM)
overridden by `limits` of problem.yaml (specs/06 §2)."""

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt, model_validator

from judge.core.package import Problem


class ResourceClass(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    cpus: PositiveFloat
    memory_mb: PositiveInt
    pids: PositiveInt
    output_kb: PositiveInt
    fst_mb: PositiveInt
    stage_timeout_s: dict[str, PositiveFloat] = Field(description="Stage type -> timeout")
    default_stage_timeout_s: PositiveFloat
    max_stage_timeout_s: PositiveFloat = Field(description="Upper bound for problem overrides")

    @model_validator(mode="after")
    def _timeouts_within_bound(self) -> "ResourceClass":
        timeouts = [self.default_stage_timeout_s, *self.stage_timeout_s.values()]
        if max(timeouts) > self.max_stage_timeout_s:
            raise ValueError("a default timeout exceeds max_stage_timeout_s")
        return self


class ResourceClasses(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    classes: dict[str, ResourceClass]


def load_resource_classes(path: Path) -> ResourceClasses:
    return ResourceClasses.model_validate({"classes": yaml.safe_load(path.read_text("utf-8"))})


@dataclass(frozen=True)
class SandboxLimits:
    """Limits of the sandbox container of one submission (specs/07 §5.1)."""

    cpus: float
    memory_mb: int
    pids: int


@dataclass(frozen=True)
class StageLimits:
    timeout_s: float
    output_bytes: int
    fst_bytes: int


def _resource_class(problem: Problem, classes: ResourceClasses) -> ResourceClass:
    try:
        return classes.classes[problem.resource_class]
    except KeyError:
        raise ValueError(f"unknown resource class {problem.resource_class!r}") from None


def sandbox_limits(problem: Problem, classes: ResourceClasses) -> SandboxLimits:
    resource = _resource_class(problem, classes)
    memory = problem.limits.memory_mb if problem.limits and problem.limits.memory_mb else None
    return SandboxLimits(resource.cpus, memory or resource.memory_mb, resource.pids)


def stage_limits(
    problem: Problem, stage_key: str, stage_type: str, classes: ResourceClasses
) -> StageLimits:
    resource = _resource_class(problem, classes)
    overrides = problem.limits
    timeout = resource.stage_timeout_s.get(stage_type, resource.default_stage_timeout_s)
    output_kb, fst_mb = resource.output_kb, resource.fst_mb
    if overrides is not None:
        timeout = overrides.stage_timeout_s.get(stage_key, timeout)
        output_kb = overrides.output_kb or output_kb
        fst_mb = overrides.fst_mb or fst_mb
    if timeout > resource.max_stage_timeout_s:
        raise ValueError(
            f"stage {stage_key}: timeout {timeout} s exceeds {resource.max_stage_timeout_s} s "
            f"of resource class {problem.resource_class}"
        )
    return StageLimits(timeout, output_kb * 1024, fst_mb * 1024 * 1024)
