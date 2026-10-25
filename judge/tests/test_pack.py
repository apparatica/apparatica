import hashlib
import os
from pathlib import Path

import pytest

from judge.core.pack import PackError, content_hash, pack, package_files, unpack


@pytest.fixture
def package(tmp_path: Path) -> Path:
    root = tmp_path / "demo"
    (root / "tb").mkdir(parents=True)
    (root / "problem.yaml").write_text("schema: 1\n", encoding="utf-8")
    (root / "tb" / "tb_top.sv").write_text("module tb_top; endmodule\n", encoding="utf-8")
    (root / "условие.md").write_text("Текст\n", encoding="utf-8")
    return root


def test_files_are_sorted_and_litter_skipped(package: Path) -> None:
    (package / ".DS_Store").write_bytes(b"x")
    (package / "tb" / "__pycache__").mkdir()
    (package / "tb" / "__pycache__" / "x.pyc").write_bytes(b"x")
    assert [f.path for f in package_files(package)] == [
        "problem.yaml",
        "tb/tb_top.sv",
        "условие.md",
    ]


def test_content_hash_is_the_sha256sum_listing(package: Path) -> None:
    files = package_files(package)
    listing = "".join(
        f"{hashlib.sha256((package / f.path).read_bytes()).hexdigest()}  {f.path}\n" for f in files
    )
    assert content_hash(files) == hashlib.sha256(listing.encode()).hexdigest()


def test_content_hash_changes_with_content_and_names(package: Path) -> None:
    before = content_hash(package_files(package))
    (package / "tb" / "tb_top.sv").write_text("module tb_top;\nendmodule\n", encoding="utf-8")
    changed = content_hash(package_files(package))
    (package / "tb" / "tb_top.sv").rename(package / "tb" / "top.sv")
    renamed = content_hash(package_files(package))
    assert len({before, changed, renamed}) == 3


def test_archive_is_deterministic(package: Path) -> None:
    first = pack(package_files(package))
    os.utime(package / "problem.yaml", (1_000_000, 1_000_000))
    (package / "tb" / "tb_top.sv").chmod(0o600)
    assert pack(package_files(package)) == first


def test_archive_round_trip(package: Path) -> None:
    files = package_files(package)
    assert unpack(pack(files)) == files


def test_symlinks_are_refused(package: Path) -> None:
    try:
        (package / "link.sv").symlink_to(package / "problem.yaml")
    except OSError:
        pytest.skip("symlinks need extra privileges on this system")
    with pytest.raises(PackError, match="symbolic links"):
        package_files(package)


def test_empty_package(tmp_path: Path) -> None:
    with pytest.raises(PackError, match="no files"):
        package_files(tmp_path)
