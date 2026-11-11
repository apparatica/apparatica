"""Problem package manifest: the `problem.yaml` model and its loading (specs/06 §2, FR-PKG-01).

The Pydantic models are the source of truth for the manifest; the JSON Schema for editors and
documentation is generated from them (`judge schema` → judge/schemas/problem.schema.json).
Stage configs beyond `type` are validated by the language module that owns the stage type.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, Self

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    StringConstraints,
    ValidationError,
    model_validator,
)

MANIFEST_NAME = "problem.yaml"
SCHEMA_ID = "https://apparatica.app/schemas/problem/1.json"

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=64)]
Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_$]*$")]
MetricRef = Annotated[str, StringConstraints(pattern=r"^[a-z_]+\.[a-z0-9_]+$")]
# `@` separates the stage key and the set id in the key of a stage instance (ADR-0014).
StageKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=32)]
ParamSetId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=32)]
ParamValue = int | str

# The id of the primary parameter set: the defaults of `interface.parameters` (ADR-0014).
PRIMARY_SET = "default"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Author(_Model):
    name: str
    github: str | None = None


class Parameter(_Model):
    name: Identifier
    type: Literal["int", "int unsigned", "bit", "logic"]
    default: ParamValue
    description: str | None = None


class DeclaredParamSet(_Model):
    """An extra parameter set (ADR-0014, specs/06 §2): the parameters it changes."""

    id: ParamSetId = Field(description=f"Unique; `{PRIMARY_SET}` is the primary set")
    values: dict[Identifier, ParamValue] = Field(
        min_length=1,
        description="Parameter -> a numeric literal; the others keep their defaults",
        examples=[{"WIDTH": 1, "DEPTH": 2}],
    )


class ResetSpec(_Model):
    active: Literal["low", "high"] | None = None
    sync: bool | None = None


class Port(_Model):
    name: Identifier
    dir: Literal["input", "output", "inout"]
    width: str = Field(description='Expression of parameters, e.g. "WIDTH" or "1"')
    signed: bool = False
    role: Literal["data", "clock", "reset"] = "data"
    reset: ResetSpec | None = None
    description: str | None = None


class Interface(_Model):
    parameters: list[Parameter] = []
    param_sets: list[DeclaredParamSet] = Field(
        default=[],
        description="Extra parameter sets of the submit stages; the primary set is the defaults",
    )
    ports: list[Port] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_names(self) -> Self:
        _require_unique("parameter", [p.name for p in self.parameters])
        _require_unique("port", [p.name for p in self.ports])
        _require_unique("parameter set", [s.id for s in self.param_sets])
        if any(s.id == PRIMARY_SET for s in self.param_sets):
            raise ValueError(f"param_sets: the id {PRIMARY_SET!r} is the primary set")
        declared = {p.name for p in self.parameters}
        for param_set in self.param_sets:
            unknown = sorted(set(param_set.values) - declared)
            if unknown:
                raise ValueError(
                    f"param_sets {param_set.id}: not in interface.parameters: {', '.join(unknown)}"
                )
        seen = {_values_key(self.param_set_values(PRIMARY_SET)): PRIMARY_SET}
        for param_set in self.param_sets:
            key = _values_key(self.param_set_values(param_set.id))
            if key in seen:
                raise ValueError(
                    f"param_sets {param_set.id}: the same values as the set {seen[key]!r}"
                )
            seen[key] = param_set.id
        return self

    def param_set_values(self, set_id: str) -> dict[str, ParamValue]:
        """Every parameter with its value at the set, in the order of `parameters`."""
        values = {p.name: p.default for p in self.parameters}
        if set_id != PRIMARY_SET:
            values |= next(s for s in self.param_sets if s.id == set_id).values
        return values


def _values_key(values: dict[str, ParamValue]) -> tuple[tuple[str, str], ...]:
    return tuple((name, str(value)) for name, value in values.items())


class Files(_Model):
    statement: str
    template: str
    statement_i18n: dict[str, str] = Field(default={}, description="Language -> statement file")


class Testbench(_Model):
    id: str
    top: Identifier
    sources: list[str] = Field(min_length=1)
    groups: dict[str, NonNegativeInt] = Field(description="Group -> expected number of tests")


StageParamSets = Literal["primary", "all"] | Annotated[list[ParamSetId], Field(min_length=1)]


class StageConfig(BaseModel):
    """`type` picks the stage plugin of the language module; the plugin validates the rest."""

    model_config = ConfigDict(extra="allow", strict=True, frozen=True)

    type: str
    param_sets: StageParamSets = Field(
        default="primary",
        description="Parameter sets the stage checks: the primary one, all of"
        " interface.param_sets too, or the primary one and the listed extra sets (ADR-0014)",
    )


class Pipeline(_Model):
    run: list[str] = Field(min_length=1)
    submit: list[str] = Field(min_length=1)


class Pipelines(_Model):
    practice: Pipeline
    industrial: dict[str, Any] | None = Field(default=None, description="Industrial mode (phase 7)")


class Limits(_Model):
    stage_timeout_s: dict[str, PositiveFloat] = {}
    memory_mb: int | None = Field(default=None, ge=128)
    output_kb: int | None = Field(default=None, ge=16)
    fst_mb: PositiveInt | None = None


class LeaderboardKey(_Model):
    metric: MetricRef = Field(description="<stage_key>.<metric>")
    dir: Literal["asc", "desc"]


class Leaderboard(_Model):
    formula_version: PositiveInt
    order: list[LeaderboardKey] = Field(min_length=1)


class ReferenceSolution(_Model):
    file: str
    title: str
    explanation: str | None = None


class Reference(_Model):
    visibility: Literal["after_accepted", "public", "hidden"] | None = None
    solutions: list[ReferenceSolution] = []


class Mutant(_Model):
    file: str
    expect: Literal["wrong_answer", "compile_error", "forbidden_construct", "limit_exceeded"]
    caught_by: list[str] = []
    note: str | None = None


class Problem(_Model):
    """The `problem.yaml` manifest."""

    model_config = ConfigDict(
        title="Apparatica problem manifest (problem.yaml)",
        json_schema_extra={"$id": SCHEMA_ID},
    )

    schema_version: Literal[1] = Field(alias="schema")
    id: Slug
    number: PositiveInt
    version: PositiveInt
    changelog: str | None = Field(
        default=None, max_length=2000, description="What changed since the previous version"
    )
    leaderboard_epoch: PositiveInt
    language: Literal["systemverilog"]
    kind: Literal["design"]
    title: str = Field(min_length=1, max_length=120)
    title_i18n: dict[str, str] = {}
    difficulty: str = Field(description="Key of config/difficulties.yaml")
    tags: list[str] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    resource_class: Literal["light", "heavy"]
    authors: list[Author] = []
    license: str | None = None
    top: Identifier
    interface: Interface
    files: Files
    testbenches: list[Testbench] = []
    stages: dict[StageKey, StageConfig]
    pipelines: Pipelines
    limits: Limits | None = None
    leaderboard: Leaderboard | None = None
    reference: Reference | None = None
    mutants: list[Mutant] = []

    @model_validator(mode="after")
    def _cross_references(self) -> Self:
        _require_unique("tag", self.tags)
        _require_unique("testbench id", [tb.id for tb in self.testbenches])
        stages = set(self.stages)
        submit = set(self.pipelines.practice.submit)
        timeouts = self.limits.stage_timeout_s if self.limits else {}
        order = self.leaderboard.order if self.leaderboard else []
        references = [
            *(("pipelines.practice.run", key) for key in self.pipelines.practice.run),
            *(("pipelines.practice.submit", key) for key in self.pipelines.practice.submit),
            *(("limits.stage_timeout_s", key) for key in timeouts),
            *(("leaderboard.order", item.metric.split(".")[0]) for item in order),
            *(("mutants.caught_by", key) for mutant in self.mutants for key in mutant.caught_by),
        ]
        unknown = [f"{where}: {key!r}" for where, key in references if key not in stages]
        if unknown:
            raise ValueError(f"unknown stage keys: {', '.join(unknown)}")
        unranked = [item.metric for item in order if item.metric.split(".")[0] not in submit]
        if unranked:
            raise ValueError(
                f"leaderboard.order: stages not in pipelines.practice.submit: {', '.join(unranked)}"
            )
        declared = {s.id for s in self.interface.param_sets}
        for key, stage in self.stages.items():
            if isinstance(stage.param_sets, str):
                continue
            _require_unique(f"stages.{key}.param_sets", stage.param_sets)
            unknown = [s for s in stage.param_sets if s not in declared]
            if unknown:
                raise ValueError(
                    f"stages.{key}.param_sets: not in interface.param_sets: {', '.join(unknown)}"
                )
        expanded = [
            k for k in self.pipelines.practice.run if self.stages[k].param_sets != "primary"
        ]
        if expanded:
            raise ValueError(
                "pipelines.practice.run checks the primary parameter set only:"
                f" param_sets of {', '.join(expanded)} must be 'primary'"
            )
        return self

    def stage_param_sets(self, key: str) -> list[str]:
        """Ids of the parameter sets of a stage: the primary set, then the extra ones in the order
        of `interface.param_sets` (ADR-0014)."""
        chosen = self.stages[key].param_sets
        extra = [
            s.id
            for s in self.interface.param_sets
            if chosen == "all" or (not isinstance(chosen, str) and s.id in chosen)
        ]
        return [PRIMARY_SET, *extra]

    def instance_keys(self, stage_keys: Sequence[str]) -> list[str]:
        """Keys of the instances of the stages in run order: by stage, at each stage the primary
        set and then the extra ones in the order of `interface.param_sets` (ADR-0014)."""
        return [instance_key(k, s) for k in stage_keys for s in self.stage_param_sets(k)]


def instance_key(stage_key: str, set_id: str) -> str:
    """Key of a stage instance (ADR-0014): the stage key at the primary set, `<key>@<set id>` at
    an extra one."""
    return stage_key if set_id == PRIMARY_SET else f"{stage_key}@{set_id}"


def split_instance_key(key: str) -> tuple[str, str]:
    """The stage key and the set id of an instance key."""
    stage_key, _, set_id = key.partition("@")
    return stage_key, set_id or PRIMARY_SET


def _require_unique(what: str, names: list[str]) -> None:
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"duplicate {what} names: {', '.join(duplicates)}")


# --- loading -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Issue:
    """One validation problem: where (a field path, or empty for the whole file) and why."""

    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}" if self.path else self.message


class ManifestError(Exception):
    def __init__(self, source: str, issues: list[Issue]) -> None:
        super().__init__(f"{source}: " + "; ".join(map(str, issues)))
        self.source = source
        self.issues = issues


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate keys instead of silently keeping the last one."""


def _construct_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    keys = [loader.construct_object(key_node) for key_node, _ in node.value]
    for key in keys:
        if keys.count(key) > 1:
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate key {key!r}", node.start_mark
            )
    return loader.construct_mapping(node)


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _format_location(location: tuple[int | str, ...]) -> str:
    path = ""
    for part in location:
        path += f"[{part}]" if isinstance(part, int) else (f".{part}" if path else part)
    return path


def parse_manifest(text: str, source: str = MANIFEST_NAME) -> Problem:
    """Parse and validate manifest text. Raises ManifestError with every issue found."""
    try:
        data = yaml.load(text, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as error:
        raise ManifestError(source, [Issue("", f"invalid YAML: {error}")]) from error
    if not isinstance(data, dict):
        raise ManifestError(source, [Issue("", "the manifest must be a mapping")])
    try:
        return Problem.model_validate(data)
    except ValidationError as error:
        issues = [
            Issue(_format_location(e["loc"]), e["msg"].removeprefix("Value error, "))
            for e in error.errors(include_url=False)
        ]
        raise ManifestError(source, issues) from error


def load_manifest(package_dir: Path) -> Problem:
    """Load `problem.yaml` of a package and check that `id` matches the directory name."""
    path = package_dir / MANIFEST_NAME
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ManifestError(str(path), [Issue("", f"cannot read: {error.strerror}")]) from error
    problem = parse_manifest(text, str(path))
    if problem.id != package_dir.resolve().name:
        raise ManifestError(
            str(path),
            [Issue("id", f"must match the package directory name {package_dir.resolve().name!r}")],
        )
    return problem


def manifest_json_schema() -> str:
    """JSON Schema of `problem.yaml`, generated from the models (draft 2020-12)."""
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema"}
    schema |= Problem.model_json_schema(by_alias=True, mode="validation")
    return json.dumps(schema, ensure_ascii=False, indent=2) + "\n"
