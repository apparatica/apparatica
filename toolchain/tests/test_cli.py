"""`judge new`, `validate` and `run` end to end in the image (specs/06 §5, FR-PKG-02/04)."""

import json
from pathlib import Path

import pytest

from judge.cli import main
from sandbox import IMAGE

ROOT = Path(__file__).parents[2]
CLASSES = ["--resource-classes", str(ROOT / "config" / "resource-classes.yaml")]
DOCKER = ["--image", IMAGE, *CLASSES]


@pytest.fixture(scope="module")
def package(tmp_path_factory: pytest.TempPathFactory) -> Path:
    problems = tmp_path_factory.mktemp("problems")
    assert main(["new", "demo-reg", "--dir", str(problems)]) == 0
    return problems / "demo-reg"


def run(package: Path, out: Path, solution: str, *extra: str) -> tuple[int, dict[str, object]]:
    args = ["run", str(package), "--solution", str(package / solution), "--out", str(out)]
    code = main([*args, *extra, *DOCKER])
    return code, json.loads((out / "result.json").read_text(encoding="utf-8"))


def test_new_package_validates(package: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(package), "--seeds", "2", *DOCKER]) == 0, capsys.readouterr().out
    out = capsys.readouterr().out
    assert out.count("ok   эталон") == 2
    assert "ok   мутант m02_ignores_en — wrong_answer, этап sim_full" in out
    assert "ok   мутант m03_initial — forbidden_construct, этап precheck" in out


def test_broken_package_fails_validation(
    package: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "demo-reg"
    broken.mkdir()
    for path in package.rglob("*"):
        if path.is_file():
            target = broken / path.relative_to(package)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
    manifest = broken / "problem.yaml"
    text = manifest.read_text(encoding="utf-8").replace("hidden: 1}", "hidden: 2}")
    manifest.write_text(text, encoding="utf-8")
    assert main(["validate", str(broken), "--seeds", "1", *DOCKER]) == 1
    out = capsys.readouterr().out
    assert "TB_GROUPS_MISMATCH — в группе hidden тестов: 1, в problem.yaml: 2" in out


def test_run_reference(package: Path, tmp_path: Path) -> None:
    code, result = run(package, tmp_path, "reference/demo_reg.sv", "--kind", "submit")
    assert code == 0
    assert result["verdict"] == {
        "status": "accepted",
        "detail": {"first_failure": None, "limit": None, "warnings": [], "error_codes": []},
    }
    events = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(events[-1]) == {"type": "done"}


def test_run_reproduces_a_failure_with_its_trace(package: Path, tmp_path: Path) -> None:
    first, second = tmp_path / "1", tmp_path / "2"
    code, result = run(package, first, "mutants/m01_reset_value.sv", "--seed", "41917")
    assert code == 1
    failure = result["verdict"]["detail"]["first_failure"]  # type: ignore[index]
    assert failure["stage"] == "sim_run"
    assert (first / "sim_run" / "trace.fst").stat().st_size > 0
    _, again = run(package, second, "mutants/m01_reset_value.sv", "--seed", "41917")
    assert again["verdict"] == result["verdict"]


def test_hidden_only_mutant_passes_run_and_fails_submit(package: Path, tmp_path: Path) -> None:
    code, _ = run(package, tmp_path / "run", "mutants/m02_ignores_en.sv")
    assert code == 0
    code, result = run(
        package, tmp_path / "submit", "mutants/m02_ignores_en.sv", "--kind", "submit"
    )
    assert code == 1
    assert result["verdict"]["status"] == "wrong_answer"  # type: ignore[index]
    assert not (tmp_path / "submit" / "sim_full" / "trace.fst").exists()  # hidden tests: no trace
