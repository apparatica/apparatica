"""Fixtures for the toolchain image tests.

Tests run on the host with pytest and execute commands in one long-lived container started with the
sandbox restrictions, the way the orchestrator uses the image (`docker exec` per command). Test
tooling therefore never gets into the sandbox image.
"""

from collections.abc import Iterator

import pytest

from sandbox import IMAGE, Sandbox


@pytest.fixture(scope="session")
def sandbox() -> Iterator[Sandbox]:
    try:
        container = Sandbox.start()
    except RuntimeError as error:
        pytest.fail(f"{error}\nBuild the image with `just toolchain-build` ({IMAGE}).")
    try:
        yield container
    finally:
        container.remove()


@pytest.fixture
def workdir(sandbox: Sandbox) -> str:
    """A fresh directory in the container's /work tmpfs."""
    return sandbox.mkdtemp()


@pytest.fixture(scope="session")
def lock(sandbox: Sandbox) -> dict[str, str]:
    """versions.lock as baked into the image."""
    entries = {}
    for line in sandbox.read("/opt/apx/versions.lock").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            entries[key] = value
    return entries
