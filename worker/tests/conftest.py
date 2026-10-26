import os
from collections.abc import Iterator

import pytest
import redis
from testcontainers.community.redis import RedisContainer

# Locally the image can come from a mirror (docs/development.md).
VALKEY_IMAGE = os.environ.get("APX_TEST_VALKEY_IMAGE", "valkey/valkey:8-alpine")


@pytest.fixture(scope="session")
def valkey_server() -> Iterator[str]:
    try:
        container = RedisContainer(VALKEY_IMAGE).start()
    except Exception as error:
        if os.environ.get("CI"):
            raise
        pytest.skip(f"Valkey tests need Docker: {error!r}")
    try:
        host, port = container.get_container_host_ip(), container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"
    finally:
        container.stop()


@pytest.fixture
def valkey_url(valkey_server: str) -> Iterator[str]:
    """valkey-queue for one test: empty before and after it."""
    client = redis.Redis.from_url(valkey_server)
    client.flushdb()
    yield valkey_server
    client.flushdb()
