import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from judge.core.package import (
    ManifestError,
    Problem,
    load_manifest,
    manifest_json_schema,
    parse_manifest,
)

DATA = Path(__file__).parent / "data"
SCHEMA_FILE = Path(__file__).parents[1] / "schemas" / "problem.schema.json"

MINIMAL: dict[str, Any] = {
    "schema": 1,
    "id": "mux4",
    "number": 1,
    "version": 1,
    "leaderboard_epoch": 1,
    "language": "systemverilog",
    "kind": "design",
    "title": "Мультиплексор 4:1",
    "difficulty": "easy",
    "tags": ["combinational"],
    "resource_class": "light",
    "top": "mux4",
    "interface": {
        "parameters": [{"name": "W", "type": "int", "default": 8}],
        "ports": [
            {"name": "sel", "dir": "input", "width": "2"},
            {"name": "y", "dir": "output", "width": "W"},
        ],
    },
    "files": {"statement": "statement.md", "template": "template.sv"},
    "stages": {"precheck": {"type": "precheck"}, "sim": {"type": "sim", "max_cycles": 1000}},
    "pipelines": {"practice": {"run": ["precheck", "sim"], "submit": ["precheck", "sim"]}},
}


def manifest(**changes: Any) -> str:
    """MINIMAL with changes applied; a dotted key sets a nested field, None removes it."""
    data = copy.deepcopy(MINIMAL)
    for dotted, value in changes.items():
        *parents, last = dotted.split("__")
        target: Any = data
        for key in parents:
            target = target[int(key)] if key.isdigit() else target[key]
        if value is None:
            del target[last]
        else:
            target[last] = value
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def issues(text: str) -> list[str]:
    with pytest.raises(ManifestError) as error:
        parse_manifest(text)
    return [str(issue) for issue in error.value.issues]


def test_spec_example_is_valid() -> None:
    problem = load_manifest(DATA / "sync-fifo")
    assert problem.id == "sync-fifo"
    assert problem.schema_version == 1
    assert [p.name for p in problem.interface.ports][:2] == ["clk", "rst_n"]
    assert problem.interface.ports[1].reset is not None
    assert problem.stages["synth"].type == "synth"
    # Plugin-specific stage fields are kept for the language module.
    assert problem.stages["sim_run"].model_extra == {
        "testbench": "main",
        "groups": ["public"],
        "max_cycles": 200000,
    }
    assert problem.limits is not None
    assert problem.limits.stage_timeout_s["sim_run"] == 20.0
    # The core takes param_sets, the language module gets the rest.
    assert problem.stages["synth"].model_extra == {"clock_period_ns": 2.0, "forbid_latches": True}
    assert problem.stage_param_sets("sim_run") == ["default"]
    assert problem.stage_param_sets("synth") == ["default", "narrow", "wide"]
    assert problem.interface.param_set_values("wide") == {"WIDTH": 32, "DEPTH": 16}
    assert problem.interface.param_set_values("default") == {"WIDTH": 8, "DEPTH": 16}


def test_minimal_manifest_and_defaults() -> None:
    problem = parse_manifest(manifest())
    assert problem.interface.ports[0].role == "data"
    assert problem.interface.ports[0].signed is False
    assert problem.mutants == []
    assert problem.limits is None


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"extra_field": 1}, "extra_field: Extra inputs are not permitted"),
        ({"number": "17"}, "number: Input should be a valid integer"),
        ({"number": 0}, "number: Input should be greater than 0"),
        ({"title": None}, "title: Field required"),
        ({"schema": 2}, "schema: Input should be 1"),
        ({"id": "Sync_FIFO"}, "id: String should match pattern"),
        ({"language": "vhdl"}, "language: Input should be 'systemverilog'"),
        ({"resource_class": "medium"}, "resource_class: Input should be 'light' or 'heavy'"),
        ({"tags": []}, "tags: List should have at least 1 item"),
        ({"tags": ["a", "a"]}, "duplicate tag names: a"),
        ({"interface__ports__0__dir": "in"}, "interface.ports[0].dir: Input should be"),
        (
            {"interface__ports__0__signed": "yes"},
            "interface.ports[0].signed: Input should be a valid boolean",
        ),
        ({"interface__ports__1__name": "sel"}, "interface: duplicate port names: sel"),
        ({"interface__ports": []}, "interface.ports: List should have at least 1 item"),
        (
            {"interface__parameters__0__type": "real"},
            "interface.parameters[0].type: Input should be",
        ),
        ({"top": "1top"}, "top: String should match pattern"),
        ({"stages__sim__type": None}, "stages.sim.type: Field required"),
        (
            {"pipelines__practice__run": ["precheck", "lint"]},
            "unknown stage keys: pipelines.practice.run: 'lint'",
        ),
        (
            {"pipelines__practice__submit": []},
            "pipelines.practice.submit: List should have at least 1 item",
        ),
        (
            {"limits": {"stage_timeout_s": {"synth": 10}}},
            "unknown stage keys: limits.stage_timeout_s: 'synth'",
        ),
        (
            {"limits": {"stage_timeout_s": {"sim": 0}}},
            "limits.stage_timeout_s.sim: Input should be greater than 0",
        ),
        (
            {"limits": {"memory_mb": 64}},
            "limits.memory_mb: Input should be greater than or equal to 128",
        ),
        (
            {
                "leaderboard": {
                    "formula_version": 1,
                    "order": [{"metric": "synth.area_um2", "dir": "asc"}],
                }
            },
            "unknown stage keys: leaderboard.order: 'synth'",
        ),
        (
            {
                "stages__synth": {"type": "synth"},
                "leaderboard": {
                    "formula_version": 1,
                    "order": [{"metric": "synth.area_um2", "dir": "asc"}],
                },
            },
            "leaderboard.order: stages not in pipelines.practice.submit: synth.area_um2",
        ),
        (
            {"leaderboard": {"formula_version": 1, "order": [{"metric": "Area", "dir": "asc"}]}},
            "leaderboard.order[0].metric: String should match pattern",
        ),
        (
            {"mutants": [{"file": "m.sv", "expect": "accepted"}]},
            "mutants[0].expect: Input should be",
        ),
        (
            {"mutants": [{"file": "m.sv", "expect": "wrong_answer", "caught_by": ["formal"]}]},
            "unknown stage keys: mutants.caught_by: 'formal'",
        ),
        (
            {
                "testbenches": [
                    {"id": "a", "top": "tb", "sources": ["tb.sv"], "groups": {"public": -1}}
                ]
            },
            "testbenches[0].groups.public: Input should be greater than or equal to 0",
        ),
        ({"reference": {"visibility": "everyone"}}, "reference.visibility: Input should be"),
        ({"changelog": "x" * 2001}, "changelog: String should have at most 2000 characters"),
        (
            {"interface__param_sets": [{"id": "default", "values": {"W": 1}}]},
            "interface: param_sets: the id 'default' is the primary set",
        ),
        (
            {"interface__param_sets": [{"id": "Narrow", "values": {"W": 1}}]},
            "interface.param_sets[0].id: String should match pattern",
        ),
        (
            {"interface__param_sets": [{"id": "a", "values": {}}]},
            "interface.param_sets[0].values: Dictionary should have at least 1 item",
        ),
        (
            {"interface__param_sets": [{"id": "a", "values": {"W": 1.5}}]},
            "interface.param_sets[0].values.W",
        ),
        (
            {"interface__param_sets": [{"id": "a", "values": {"N": 1}}]},
            "interface: param_sets a: not in interface.parameters: N",
        ),
        (
            {
                "interface__param_sets": [
                    {"id": "a", "values": {"W": 1}},
                    {"id": "a", "values": {"W": 2}},
                ]
            },
            "interface: duplicate parameter set names: a",
        ),
        (
            {"interface__param_sets": [{"id": "a", "values": {"W": 8}}]},
            "interface: param_sets a: the same values as the set 'default'",
        ),
        (
            {
                "interface__param_sets": [
                    {"id": "a", "values": {"W": 1}},
                    {"id": "b", "values": {"W": "1"}},
                ]
            },
            "interface: param_sets b: the same values as the set 'a'",
        ),
        ({"stages__sim__param_sets": "some"}, "stages.sim.param_sets"),
        ({"stages__sim__param_sets": []}, "stages.sim.param_sets"),
        (
            {"stages__sim__param_sets": ["narrow"]},
            "stages.sim.param_sets: not in interface.param_sets: narrow",
        ),
        (
            {
                "interface__param_sets": [{"id": "narrow", "values": {"W": 1}}],
                "stages__sim__param_sets": ["narrow", "narrow"],
            },
            "duplicate stages.sim.param_sets names: narrow",
        ),
        (
            {"stages__sim__param_sets": "all"},
            "pipelines.practice.run checks the primary parameter set only:"
            " param_sets of sim must be 'primary'",
        ),
    ],
)
def test_invalid_manifest_reports_path_and_reason(changes: dict[str, Any], expected: str) -> None:
    found = issues(manifest(**changes))
    assert any(expected in issue for issue in found), found


def test_stage_parameter_sets_keep_the_order_of_the_interface() -> None:
    sets = [{"id": name, "values": {"W": n}} for n, name in enumerate(["a", "b", "c"], start=1)]
    stages = {
        "precheck": {"type": "precheck"},
        "sim": {"type": "sim"},
        "some": {"type": "sim", "param_sets": ["c", "a"]},
        "every": {"type": "sim", "param_sets": "all"},
    }
    problem = parse_manifest(
        manifest(
            interface__param_sets=sets,
            stages=stages,
            pipelines__practice__submit=["precheck", "sim", "some", "every"],
        )
    )
    assert problem.stage_param_sets("sim") == ["default"]
    assert problem.stage_param_sets("some") == ["default", "a", "c"]
    assert problem.stage_param_sets("every") == ["default", "a", "b", "c"]
    assert problem.interface.param_set_values("b") == {"W": 2}


def test_all_issues_are_reported_at_once() -> None:
    found = issues(manifest(number="1", kind="testbench", extra=True))
    assert len(found) == 3


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("schema: 1\nid: a\nid: b\n", "invalid YAML: duplicate key 'id'"),
        ("schema: [1\n", "invalid YAML"),
        ("- a\n- b\n", "the manifest must be a mapping"),
        ("", "the manifest must be a mapping"),
    ],
)
def test_malformed_yaml(text: str, expected: str) -> None:
    assert any(expected in issue for issue in issues(text))


def test_id_must_match_directory(tmp_path: Path) -> None:
    package = tmp_path / "other-name"
    package.mkdir()
    (package / "problem.yaml").write_text(manifest(), encoding="utf-8")
    with pytest.raises(ManifestError) as error:
        load_manifest(package)
    assert [str(i) for i in error.value.issues] == [
        "id: must match the package directory name 'other-name'"
    ]


def test_missing_manifest(tmp_path: Path) -> None:
    with pytest.raises(ManifestError) as error:
        load_manifest(tmp_path)
    assert "cannot read" in str(error.value.issues[0])


def test_models_are_immutable() -> None:
    problem = parse_manifest(manifest())
    with pytest.raises(ValueError, match="frozen"):
        problem.version = 2
    assert isinstance(problem, Problem)


def test_committed_json_schema_is_up_to_date() -> None:
    assert SCHEMA_FILE.read_text(encoding="utf-8") == manifest_json_schema(), (
        "judge/schemas/problem.schema.json is stale: run `just schemas`"
    )
