import json
import shutil
from pathlib import Path

import pytest

from judge.cli import main

DATA = Path(__file__).parent / "data"


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


def test_full_validation_is_not_implemented_yet(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(DATA / "sync-fifo")]) == 2
    assert "--schema-only" in capsys.readouterr().err


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
