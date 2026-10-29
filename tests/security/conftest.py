"""Fixtures of the security suite (specs/09 §4.2, NFR-SEC-04).

apx-sandboxd runs in the test process on loopback TCP, with the policy of a worker host; every check
gets a sandbox of its own and destroys it, like a submission. After each test the host must be
unharmed: no sandbox is left behind and the daemon still creates working sandboxes.
"""

import asyncio
import threading
from collections.abc import Iterator, Sequence

import pytest

from apparatica_worker.sandboxd.client import SandboxdClient, SandboxExecutor
from apparatica_worker.sandboxd.server import (
    DOCKER_TIMEOUT_S,
    MAX_REQUEST,
    DockerCli,
    Policy,
    Sandboxd,
    repository,
)
from harness import IMAGE, LIMITS, RUNTIME, sandbox_containers, sh, stage


class Docker(DockerCli):
    """The docker CLI that remembers the sandboxes it created: other runs may share the host."""

    def __init__(self) -> None:
        self.created: set[str] = set()

    async def run(
        self, args: Sequence[str], *, stdin: bytes | None = None, timeout: float = DOCKER_TIMEOUT_S
    ) -> tuple[int, bytes, bytes]:
        if args[0] == "run":
            self.created.add(args[args.index("--name") + 1])
        return await super().run(args, stdin=stdin, timeout=timeout)


@pytest.fixture(scope="session")
def docker() -> Docker:
    return Docker()


@pytest.fixture(scope="session")
def sandboxd(docker: Docker) -> Iterator[tuple[Sandboxd, tuple[str, int]]]:
    """The daemon and its address."""
    policy = Policy(
        runtime=RUNTIME,
        images=frozenset({repository(IMAGE)}),
        ceiling=LIMITS,
        max_sandboxes=2,
        max_lifetime_s=3600,
    )
    daemon = Sandboxd(policy, docker)
    loop = asyncio.new_event_loop()
    server = loop.run_until_complete(
        asyncio.start_server(daemon.handle, "127.0.0.1", 0, limit=MAX_REQUEST)
    )
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    yield daemon, ("127.0.0.1", server.sockets[0].getsockname()[1])
    loop.call_soon_threadsafe(loop.stop)
    thread.join()
    server.close()
    loop.close()


@pytest.fixture
def client(sandboxd: tuple[Sandboxd, tuple[str, int]], docker: Docker) -> Iterator[SandboxdClient]:
    daemon, address = sandboxd
    yield SandboxdClient(address)
    assert not daemon.sandboxes, "a sandbox outlived its check"
    assert not docker.created & set(sandbox_containers()), "a sandbox container is left on the host"
    with SandboxExecutor(SandboxdClient(address), IMAGE, LIMITS) as executor:
        assert stage(executor, "after", sh("true"))[0].ok, "the host cannot start a sandbox"
