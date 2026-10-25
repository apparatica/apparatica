import json
import shutil
from pathlib import Path

import pytest

from judge.cli import main
from judge.core.pack import content_hash, package_files, unpack

DATA = Path(__file__).parent / "data"
RESOURCE_CLASSES = Path(__file__).parents[2] / "config" / "resource-classes.yaml"


@pytest.fixture
def problems(tmp_path: Path) -> Path:
    """A problems/ directory with one valid and one invalid package."""
    shutil.copytree(DATA / "sync-fifo", tmp_path / "sync-fifo")
    broken = tmp_path / "broken"
    broken.mkdir()
    text = (DATA / "sync-fifo" / "problem.yaml").read_text(encoding="utf-8")
    (broken / "problem.yaml").write_text(
        text.replace("id: sync-fifo", "id: broken").replace("dir: input", "dir: in", 1),
        encoding="utf-8",
    )
    return tmp_path


def test_validate_valid_package(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", "--schema-only", str(DATA / "sync-fifo")]) == 0
    assert capsys.readouterr().out.startswith("ok ")


def test_validate_directory_of_packages(problems: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", "--schema-only", str(problems)]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "interface.ports[0].dir: Input should be 'input', 'output' or 'inout'" in out
    assert out.count("ok ") == 1


def test_validate_missing_package(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", "--schema-only", str(tmp_path / "nope")]) == 1
    assert "cannot read" in capsys.readouterr().out


def test_full_validation_stops_at_schema_errors(
    problems: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The broken package fails before anything runs; sync-fifo has no reference files.
    assert main(["validate", "--resource-classes", str(RESOURCE_CLASSES), str(problems)]) == 1
    out = capsys.readouterr().out
    assert "FAIL схема problem.yaml — interface.ports[0].dir" in out
    assert "невалидных пакетов: 2 из 2" in out


def test_validate_needs_resource_classes(
    problems: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(problems)
    monkeypatch.delenv("JUDGE_RESOURCE_CLASSES", raising=False)
    assert main(["validate", str(problems / "sync-fifo")]) == 2
    assert "config/resource-classes.yaml" in capsys.readouterr().err


def test_new_and_pack(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["new", "demo-reg", "--dir", str(tmp_path)]) == 0
    package = tmp_path / "demo-reg"
    assert (package / "reference" / "demo_reg.sv").is_file()
    capsys.readouterr()
    archive = tmp_path / "demo.tar.zst"
    assert main(["pack", str(package), "--output", str(archive)]) == 0
    out = capsys.readouterr().out
    assert f"content_hash {content_hash(package_files(package))}" in out
    assert unpack(archive.read_bytes()) == package_files(package)
    assert main(["new", "demo-reg", "--dir", str(tmp_path)]) == 2  # exists


def test_run_reports_a_missing_solution(capsys: pytest.CaptureFixture[str]) -> None:
    args = ["run", str(DATA / "sync-fifo"), "--solution", "missing.sv"]
    assert main(args) == 2
    assert "missing.sv" in capsys.readouterr().err


def test_schema_prints_json_schema(capsysbinary: pytest.CaptureFixture[bytes]) -> None:
    assert main(["schema"]) == 0
    schema = json.loads(capsysbinary.readouterr().out.decode("utf-8"))
    assert schema["$id"] == "https://apparatica.app/schemas/problem/1.json"
    assert schema["additionalProperties"] is False
    assert "schema" in schema["required"]


def test_schema_of_tb_result(capsysbinary: pytest.CaptureFixture[bytes]) -> None:
    assert main(["schema", "tb-result"]) == 0
    schema = json.loads(capsysbinary.readouterr().out.decode("utf-8"))
    assert schema["$id"] == "https://apparatica.app/schemas/tb-result/1.json"
    assert "suite_start" in schema["discriminator"]["mapping"]


def test_schema_output_file(tmp_path: Path) -> None:
    target = tmp_path / "problem.schema.json"
    assert main(["schema", "--output", str(target)]) == 0
    assert b"\r\n" not in target.read_bytes()
    assert json.loads(target.read_text(encoding="utf-8"))["type"] == "object"


def test_command_is_required() -> None:
    with pytest.raises(SystemExit):
        main([])
