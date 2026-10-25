from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apparatica.core.settings import Settings
from apparatica.main import create_app

CONFIG_DIR = Path(__file__).parents[2] / "config"


@pytest.fixture
def settings() -> Settings:
    # SQLite in memory stands in for Postgres where only connectivity matters.
    return Settings(
        environment="test", database_url="sqlite+aiosqlite:///:memory:", config_dir=CONFIG_DIR
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
        yield test_client
