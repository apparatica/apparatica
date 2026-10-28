"""`apparatica-admin problems import` (FR-PKG-06) on Postgres, with S3 emulated by moto."""

import asyncio
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import boto3
import pytest
from moto import mock_aws
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from apparatica.admin.cli import main
from apparatica.core.settings import get_settings
from conftest import CONFIG_DIR, repo_version
from judge.core.pack import content_hash, unpack

PROBLEMS = Path(__file__).parents[2] / "problems"
V = repo_version("mux4")  # the version of mux4 in the repository
REGION = "us-east-1"


@pytest.fixture
def s3(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    for name, value in {
        "APX_DATABASE_URL": database_url,
        "APX_CONFIG_DIR": str(CONFIG_DIR),
        "APX_S3_REGION": REGION,
        "APX_S3_ACCESS_KEY_ID": "test",
        "APX_S3_SECRET_ACCESS_KEY": "test",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    with mock_aws():
        client = boto3.client("s3", region_name=REGION)
        client.create_bucket(Bucket="packages")
        yield client
    get_settings.cache_clear()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A copy of problems/ that tests can change."""
    root = tmp_path / "problems"
    shutil.copytree(PROBLEMS, root)
    return root


def query(sql: str) -> list[tuple[Any, ...]]:
    async def run() -> list[tuple[Any, ...]]:
        engine = create_async_engine(get_settings().database_url)
        try:
            async with engine.connect() as connection:
                return [tuple(row) for row in await connection.execute(text(sql))]
        finally:
            await engine.dispose()

    return asyncio.run(run())


def replace(path: Path, old: str, new: str) -> None:
    # Bytes: text mode on Windows would change line endings and so the content hash.
    content = path.read_bytes()
    assert old.encode() in content
    path.write_bytes(content.replace(old.encode(), new.encode()))


def keys(s3: Any) -> list[str]:
    return sorted(item["Key"] for item in s3.list_objects_v2(Bucket="packages").get("Contents", []))


def test_import_of_the_repository(s3: Any, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["problems", "import", "--publish", str(PROBLEMS)]) == 0
    assert "новых версий: 5, без изменений: 0" in capsys.readouterr().out

    problems = query(
        "SELECT p.slug, p.number, p.is_published, v.version, v.title, v.package_uri"
        " FROM problems p JOIN problem_versions v ON v.id = p.current_version_id ORDER BY p.number"
    )
    slugs = ["mux4", "counter-mod-n", "carry-adder", "seq-detector", "sync-fifo"]
    assert [row[:4] for row in problems] == [
        (slug, number, True, repo_version(slug)) for number, slug in enumerate(slugs, start=1)
    ]
    assert problems[0][4] == "Мультиплексор 4:1"

    # The stored archive is the package: its content hash is in the key and in the version.
    assert keys(s3) == sorted(row[5] for row in problems)
    [(stored_hash, package_uri)] = query(
        "SELECT content_hash, package_uri FROM problem_versions WHERE package_uri LIKE 'mux4/%'"
    )
    archive = s3.get_object(Bucket="packages", Key=package_uri)
    assert content_hash(unpack(archive["Body"].read())) == stored_hash
    assert archive["ContentType"] == "application/zstd"

    [(manifest, statement, tags)] = query(
        "SELECT manifest, statement_md, tags FROM problem_versions WHERE package_uri LIKE 'mux4/%'"
    )
    assert manifest["schema"] == 1
    assert manifest["top"] == "mux4"
    assert statement == (PROBLEMS / "mux4" / "statement.md").read_bytes().decode()
    assert tags == ["combinational", "multiplexer"]
    assert query("SELECT count(*) FROM reference_solutions WHERE explanation_md <> ''") == [(5,)]
    assert query("SELECT slug, title, sort FROM tags ORDER BY sort")[:2] == [
        ("combinational", "комбинационная логика", 0),
        ("sequential", "последовательностная логика", 1),
    ]

    assert main(["problems", "import", "--publish", str(PROBLEMS)]) == 0
    assert "новых версий: 0, без изменений: 5" in capsys.readouterr().out
    assert query("SELECT count(*) FROM problem_versions") == [(5,)]


def test_a_published_version_is_immutable(
    s3: Any, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["problems", "import", "--publish", str(repo / "mux4")]) == 0
    statement = repo / "mux4" / "statement.md"
    statement.write_bytes(statement.read_bytes() + "Уточнение.\n".encode())
    assert main(["problems", "import", str(repo / "mux4")]) == 1
    out = capsys.readouterr().out
    assert f"FAIL mux4 v{V}: the version is already imported with content hash" in out
    assert "increase `version`" in out

    replace(repo / "mux4" / "problem.yaml", f"version: {V}", f"version: {V + 1}")
    assert main(["problems", "import", str(repo / "mux4")]) == 0
    current = (
        "SELECT v.version FROM problems p JOIN problem_versions v ON v.id = p.current_version_id"
    )
    assert query(current) == [(V,)]  # without --publish the new version is not current
    assert main(["problems", "import", "--publish", str(repo / "mux4")]) == 0
    assert query(current) == [(V + 1,)]
    assert len(keys(s3)) == 2

    replace(repo / "mux4" / "problem.yaml", f"version: {V + 1}", f"version: {V}")
    replace(statement, "Уточнение.\n", "")
    assert main(["problems", "import", "--publish", str(repo / "mux4")]) == 1
    assert f"FAIL mux4 v{V}: older than the current version {V + 1}" in capsys.readouterr().out


def test_an_import_is_all_or_nothing(
    s3: Any, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clone = repo / "mux4-clone"
    shutil.copytree(repo / "mux4", clone)
    replace(clone / "problem.yaml", "id: mux4", "id: mux4-clone")  # the number stays 1
    assert (
        main(["problems", "import", str(repo / "counter-mod-n"), str(repo / "mux4"), str(clone)])
        == 1
    )
    assert f"FAIL mux4-clone v{V}: number 1 belongs to 'mux4'" in capsys.readouterr().out
    assert query("SELECT count(*) FROM problems") == [(0,)]
    assert query("SELECT count(*) FROM tags") == [(0,)]
    assert keys(s3) == []

    replace(repo / "mux4" / "problem.yaml", "difficulty: easy", "difficulty: trivial")
    replace(repo / "carry-adder" / "problem.yaml", "arithmetic]", "adders]")
    assert main(["problems", "import", str(repo)]) == 1
    out = capsys.readouterr().out
    assert f"FAIL mux4 v{V}: difficulty 'trivial' is not in difficulties.yaml" in out
    adder = repo_version("carry-adder")
    assert f"FAIL carry-adder v{adder}: tags not in tags.yaml: adders" in out


def test_broken_packages_and_catalogues(
    s3: Any, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    replace(repo / "mux4" / "problem.yaml", "number: 1", "number: 0")
    assert main(["problems", "import", str(repo)]) == 1
    out = capsys.readouterr().out
    assert "number: Input should be greater than 0" in out

    replace(repo / "mux4" / "problem.yaml", "number: 0", "number: 1")
    (repo / "tags.yaml").write_bytes(b"- {slug: fsm, title: FSM}\n- {slug: fsm, title: x}\n")
    assert main(["problems", "import", str(repo)]) == 1
    assert "duplicate tags: fsm" in capsys.readouterr().out
    assert main(["problems", "import", "--tags", str(PROBLEMS / "tags.yaml"), str(repo)]) == 0
