import sqlite3
from pathlib import Path

import pytest

from apparatica.cli import alembic_config, main
from apparatica.core.settings import get_settings


def test_migrate_runs_against_an_empty_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "db.sqlite"
    monkeypatch.setenv("APX_DATABASE_URL", f"sqlite+aiosqlite:///{database.as_posix()}")
    get_settings.cache_clear()
    try:
        assert main(["migrate"]) == 0
    finally:
        get_settings.cache_clear()
    with sqlite3.connect(database) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
    assert "alembic_version" in tables


def test_alembic_finds_the_migrations_in_the_package() -> None:
    config = alembic_config()
    assert config.get_main_option("script_location") == "apparatica:migrations"
