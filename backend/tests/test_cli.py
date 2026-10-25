import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from apparatica.cli import alembic_config, main
from apparatica.core.settings import get_settings
from conftest import Postgres


def test_migrate_creates_the_schema(postgres: Postgres, monkeypatch: pytest.MonkeyPatch) -> None:
    url = postgres.create_database()
    monkeypatch.setenv("APX_DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        assert main(["migrate"]) == 0
    finally:
        get_settings.cache_clear()

    async def state() -> tuple[str | None, set[str]]:
        engine = create_async_engine(url)
        try:
            async with engine.connect() as connection:
                revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
                tables = await connection.scalars(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
                return revision, set(tables)
        finally:
            await engine.dispose()

    revision, tables = asyncio.run(state())
    assert revision == "0001"
    assert {"problems", "submissions", "feature_flags"} <= tables


def test_alembic_finds_the_migrations_in_the_package() -> None:
    config = alembic_config()
    assert config.get_main_option("script_location") == "apparatica:migrations"
