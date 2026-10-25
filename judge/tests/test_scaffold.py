from pathlib import Path

import pytest

from judge.core.package import load_manifest
from judge.core.scaffold import ScaffoldError, create_package, next_number, top_name
from judge.languages.systemverilog import LANGUAGE


def test_creates_a_loadable_package(tmp_path: Path) -> None:
    written = create_package(LANGUAGE, tmp_path, "shift-reg")
    package = tmp_path / "shift-reg"
    names = sorted(p.relative_to(package).as_posix() for p in written)
    assert "reference/shift_reg.sv" in names
    assert "tb/tb_top.sv" in names
    problem = load_manifest(package)
    assert (problem.id, problem.top, problem.number) == ("shift-reg", "shift_reg", 1)
    for path in written:
        assert "__top__" not in path.read_text(encoding="utf-8"), path
    assert "module shift_reg_model" in (package / "tb" / "model.sv").read_text(encoding="utf-8")


def test_number_follows_the_existing_packages(tmp_path: Path) -> None:
    create_package(LANGUAGE, tmp_path, "first")
    (tmp_path / "first" / "problem.yaml").write_text(
        (tmp_path / "first" / "problem.yaml")
        .read_text(encoding="utf-8")
        .replace("number: 1", "number: 41"),
        encoding="utf-8",
    )
    (tmp_path / "junk").mkdir()
    (tmp_path / "junk" / "problem.yaml").write_text("[not a mapping", encoding="utf-8")
    assert next_number(tmp_path) == 42
    create_package(LANGUAGE, tmp_path, "second")
    assert load_manifest(tmp_path / "second").number == 42


@pytest.mark.parametrize(
    ("slug", "top"), [("sync-fifo", "sync_fifo"), ("4bit-adder", "m_4bit_adder")]
)
def test_top_name(slug: str, top: str) -> None:
    assert top_name(slug) == top


@pytest.mark.parametrize("slug", ["Sync", "a_b", "-a", "a--b", ""])
def test_bad_slug(tmp_path: Path, slug: str) -> None:
    with pytest.raises(ScaffoldError, match="not a slug"):
        create_package(LANGUAGE, tmp_path, slug)


def test_existing_package(tmp_path: Path) -> None:
    (tmp_path / "taken").mkdir()
    with pytest.raises(ScaffoldError, match="already exists"):
        create_package(LANGUAGE, tmp_path, "taken")
