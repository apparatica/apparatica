"""`judge validate` checks on a fake language: a stage judges the solution by a marker in it."""

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

import pytest
import yaml
from core_helpers import RESOURCE_CLASSES
from pydantic import BaseModel, ConfigDict

from judge.core.executor import HostExecutor
from judge.core.package import Problem, load_manifest
from judge.core.registry import LanguageModule
from judge.core.stage import (
    Command,
    ExecResult,
    StageContext,
    StageOutcome,
    StagePlan,
    StageSummary,
)
from judge.core.validate import (
    Check,
    PackageValidator,
    _caught_in_time,
    validation_seeds,
)


class MarkerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    catches: str = "WRONG"  # the marker this stage fails on
    kind: str = "wrong"


class MarkerStage:
    """Fails with `kind` if the solution contains `catches`; the check runs as a command."""

    stage_type: ClassVar[str] = "marker"
    config_model: ClassVar[type[BaseModel]] = MarkerConfig
    metrics_schema: ClassVar[str | None] = None

    def plan(self, ctx: StageContext) -> StagePlan:
        assert isinstance(ctx.config, MarkerConfig)
        # Artifacts: result.bin is random for solutions marked RANDOM, trace.fst always is.
        code = (
            "import os, sys; text = open('solution.sv').read(); "
            "open('result.bin', 'wb').write(os.urandom(8) if 'RANDOM' in text else b'same'); "
            "open('trace.fst', 'wb').write(os.urandom(8)); "
            f"sys.exit({ctx.config.catches!r} in text)"
        )
        return StagePlan(
            commands=(Command((sys.executable, "-c", code)),),
            timeout_s=10,
            output_limit=1 << 16,
            inputs={"solution.sv": ctx.solution},
            collect=("result.bin", "trace.fst"),
        )

    def interpret(self, ctx: StageContext, runs: Sequence[ExecResult]) -> StageOutcome | StagePlan:
        assert isinstance(ctx.config, MarkerConfig)
        if runs[-1].ok:
            return StageOutcome(status="passed", artifacts=dict(runs[-1].files))
        caption = f"нашёл {ctx.config.catches}"
        return StageOutcome(
            status="failed",
            failure_kind=ctx.config.kind,  # type: ignore[arg-type]
            summary=StageSummary(caption=caption),
        )


FAKE = LanguageModule(
    name="systemverilog", stages={"marker": MarkerStage}, template_checks=("marker",)
)

STAGES = {
    "check": {"type": "marker", "catches": "FORBIDDEN", "kind": "forbidden"},
    "early": {"type": "marker", "catches": "EARLY"},
    "late": {"type": "marker", "catches": "WRONG"},
}


def write_package(root: Path, **changes: object) -> Path:
    package = root / "demo"
    package.mkdir()
    files = {
        "statement.md": "Условие\n",
        "template.sv": "module demo; endmodule\n",
        "reference/demo.sv": "module demo; // good\nendmodule\n",
        "mutants/m01.sv": "WRONG\n",
        "mutants/m02.sv": "FORBIDDEN\n",
    }
    for name, text in files.items():
        (package / name).parent.mkdir(parents=True, exist_ok=True)
        (package / name).write_text(text, encoding="utf-8")
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
        "stages": STAGES,
        "pipelines": {"practice": {"run": ["check"], "submit": ["check", "early", "late"]}},
        "reference": {"solutions": [{"file": "reference/demo.sv", "title": "Эталон"}]},
        "mutants": [
            {"file": "mutants/m01.sv", "expect": "wrong_answer", "caught_by": ["late"]},
            {"file": "mutants/m02.sv", "expect": "forbidden_construct"},
        ],
    } | changes
    (package / "problem.yaml").write_text(yaml.safe_dump(manifest, allow_unicode=True), "utf-8")
    return package


def validate(package: Path, seeds: int = 2, determinism: bool = False) -> list[Check]:
    validator = PackageValidator(
        lambda problem: HostExecutor(),
        RESOURCE_CLASSES,
        seeds=seeds,
        determinism=determinism,
        language_lookup=lambda name: FAKE,
    )
    return validator.validate(package)


def failures(checks: list[Check]) -> list[str]:
    return [f"{c.what}: {c.detail}" for c in checks if c.status == "fail"]


def test_valid_package(tmp_path: Path) -> None:
    checks = validate(write_package(tmp_path))
    assert failures(checks) == []
    whats = [c.what for c in checks]
    assert whats[:4] == ["схема problem.yaml", "этапы и лимиты", "файлы пакета", "условие"]
    assert whats[4] == "шаблон template.sv"
    assert sum(w.startswith("эталон reference/demo.sv") for w in whats) == 2
    assert [c.detail for c in checks if c.what.startswith("мутант")] == [
        "wrong_answer, этап late",
        "forbidden_construct, этап check",
    ]


def test_schema_error_stops(tmp_path: Path) -> None:
    checks = validate(write_package(tmp_path, number=0))
    assert [(c.status, c.what) for c in checks] == [("fail", "схема problem.yaml")]


def test_unknown_stage_type(tmp_path: Path) -> None:
    package = write_package(tmp_path, stages=STAGES | {"late": {"type": "synth"}})
    assert failures(validate(package)) == [
        "этапы и лимиты: stage late: language systemverilog has no stage type 'synth'"
    ]


def test_invalid_stage_config(tmp_path: Path) -> None:
    package = write_package(tmp_path, stages=STAGES | {"late": {"type": "marker", "x": 1}})
    assert "stage late" in failures(validate(package))[0]


def test_missing_files(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    (package / "mutants" / "m02.sv").unlink()
    assert failures(validate(package)) == ["файлы пакета: нет файлов: mutants/m02.sv"]


def test_files_outside_the_package(tmp_path: Path) -> None:
    (tmp_path / "secret.sv").write_text("x", encoding="utf-8")
    package = write_package(
        tmp_path, files={"statement": "../secret.sv", "template": "template.sv"}
    )
    assert failures(validate(package)) == ["файлы пакета: нет файлов: ../secret.sv"]


def test_statement_must_be_utf8(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    (package / "statement.md").write_bytes(b"\xff\xfe")
    assert failures(validate(package)) == ["условие: statement.md: не UTF-8"]


def test_failing_template(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    (package / "template.sv").write_text("FORBIDDEN\n", encoding="utf-8")
    assert failures(validate(package)) == [
        "шаблон template.sv: forbidden_construct: этап check — нашёл FORBIDDEN"
    ]


def test_failing_reference_on_every_seed(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    (package / "reference" / "demo.sv").write_text("WRONG\n", encoding="utf-8")
    failed = failures(validate(package, seeds=3))
    assert len(failed) == 3
    assert failed[0].endswith("wrong_answer: этап late — нашёл WRONG")


def test_determinism_of_a_stable_reference(tmp_path: Path) -> None:
    # trace.fst differs between the runs and is ignored, result.bin is equal.
    checks = validate(write_package(tmp_path), determinism=True)
    assert failures(checks) == []
    assert [c.what for c in checks if c.what.startswith("детерминизм")] == [
        f"детерминизм reference/demo.sv, сид {validation_seeds(_problem(tmp_path), 1)[0]}"
    ]


def test_determinism_catches_a_changing_artifact(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    (package / "reference" / "demo.sv").write_text("RANDOM\n", encoding="utf-8")
    failed = failures(validate(package, determinism=True))
    assert len(failed) == 1
    assert failed[0].endswith("второй прогон отличается: артефакт check/result.bin")


def test_no_determinism_check_by_default(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    (package / "reference" / "demo.sv").write_text("RANDOM\n", encoding="utf-8")
    assert failures(validate(package)) == []


def _problem(tmp_path: Path) -> Problem:
    return load_manifest(tmp_path / "demo")


def test_reference_is_required(tmp_path: Path) -> None:
    package = write_package(tmp_path, reference=None)
    assert failures(validate(package)) == ["эталоны: нет эталонного решения (reference.solutions)"]


def test_uncaught_mutant(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    (package / "mutants" / "m01.sv").write_text("fine\n", encoding="utf-8")
    assert failures(validate(package)) == [
        "мутант m01: мутант m01 не пойман (ожидался wrong_answer)"
    ]


def test_mutant_with_another_verdict(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    (package / "mutants" / "m02.sv").write_text("WRONG\n", encoding="utf-8")
    assert failures(validate(package)) == [
        "мутант m02: ожидался forbidden_construct, получено wrong_answer: этап late — нашёл WRONG"
    ]


def test_mutant_caught_earlier_passes(tmp_path: Path) -> None:
    package = write_package(tmp_path)
    (package / "mutants" / "m01.sv").write_text("EARLY\n", encoding="utf-8")
    assert failures(validate(package)) == []


def test_mutant_caught_later_fails(tmp_path: Path) -> None:
    package = write_package(
        tmp_path,
        mutants=[{"file": "mutants/m01.sv", "expect": "wrong_answer", "caught_by": ["early"]}],
    )
    assert failures(validate(package)) == [
        "мутант m01: пойман этапом late, а должен — early или раньше"
    ]


@pytest.mark.parametrize(
    ("stage", "caught_by", "ok"),
    [
        ("late", [], True),
        ("late", ["late"], True),
        ("early", ["late"], True),
        ("late", ["early"], False),
        ("late", ["run_only"], False),  # not in the submit pipeline: only an exact match counts
        (None, ["late"], False),
    ],
)
def test_caught_in_time(stage: str | None, caught_by: list[str], ok: bool) -> None:
    assert _caught_in_time(stage, caught_by, ["check", "early", "late"]) is ok


def test_validation_seeds(tmp_path: Path) -> None:
    problem = load_manifest(write_package(tmp_path))
    seeds = validation_seeds(problem, 3)
    assert seeds == validation_seeds(problem, 3)
    assert len(set(seeds)) == 3
    assert all(0 <= seed < 2**63 for seed in seeds)
    newer = problem.model_copy(update={"version": 2})
    assert validation_seeds(newer, 1) != seeds[:1]
