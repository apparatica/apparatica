import asyncio
import itertools
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.postgres import PostgresContainer

from apparatica.cli import alembic_config
from apparatica.core.flags import no_overrides
from apparatica.core.settings import Settings
from apparatica.main import create_app

CONFIG_DIR = Path(__file__).parents[2] / "config"
# Locally the image can come from a mirror (docs/development.md).
POSTGRES_IMAGE = os.environ.get("APX_TEST_POSTGRES_IMAGE", "postgres:17-alpine")


@pytest.fixture
def settings() -> Settings:
    # SQLite in memory stands in for Postgres where only connectivity matters.
    return Settings(
        environment="test", database_url="sqlite+aiosqlite:///:memory:", config_dir=CONFIG_DIR
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings, flag_overrides=no_overrides)  # the SQLite database has no tables
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


class Postgres:
    """One Postgres server per test session; tests get their own databases."""

    MIGRATED = "migrated"  # the template: the schema at the head revision

    def __init__(self, container: PostgresContainer) -> None:
        self._url = make_url(container.get_connection_url())
        self._names = (f"test_{n}" for n in itertools.count())

    def url(self, database: str) -> str:
        return self._url.set(database=database).render_as_string(hide_password=False)

    def create_database(self, template: str | None = None) -> str:
        name = next(self._names)
        statement = f"CREATE DATABASE {name}" + (f" TEMPLATE {template}" if template else "")
        asyncio.run(self.execute(statement))
        return self.url(name)

    async def execute(self, statement: str) -> None:
        engine = create_async_engine(self.url("postgres"), isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as connection:
                await connection.execute(text(statement))
        finally:
            await engine.dispose()


@pytest.fixture(scope="session")
def postgres() -> Iterator[Postgres]:
    try:
        container = PostgresContainer(POSTGRES_IMAGE, driver="asyncpg").start()
    except Exception as error:
        if os.environ.get("CI"):
            raise
        pytest.skip(f"Postgres tests need Docker: {error!r}")
    try:
        server = Postgres(container)
        asyncio.run(server.execute(f"CREATE DATABASE {Postgres.MIGRATED}"))
        command.upgrade(alembic_config(server.url(Postgres.MIGRATED)), "head")
        yield server
    finally:
        container.stop()


@pytest.fixture
def database_url(postgres: Postgres) -> str:
    """A fresh database with the schema of the head revision."""
    return postgres.create_database(template=Postgres.MIGRATED)
