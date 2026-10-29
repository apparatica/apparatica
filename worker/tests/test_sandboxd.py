"""apx-sandboxd without Docker: what it asks of Docker and what it refuses (specs/07 §5.3)."""

import asyncio
import socket
import sys
import threading
import time
from collections.abc import Iterator, Sequence
from typing import Any

import pytest

from apparatica_worker.sandboxd.client import SandboxContainer, SandboxdClient
from apparatica_worker.sandboxd.server import (
    LABEL,
    MAX_REQUEST,
    Policy,
    Process,
    Sandboxd,
    _Sandbox,
    repository,
)
from judge.core.executor import ExecutorError, SandboxLostError
from judge.core.limits import SandboxLimits

IMAGE = "ghcr.io/apparatica/toolchain@sha256:" + "a" * 64
LIMITS = SandboxLimits(cpus=2, memory_mb=2048, pids=256)
POLICY = Policy(
    runtime="runsc",
    images=frozenset({"ghcr.io/apparatica/toolchain"}),
    ceiling=SandboxLimits(cpus=4, memory_mb=8192, pids=256),
    max_sandboxes=2,
    max_lifetime_s=3600,
)
# What `docker exec` of the fake prints: the size of its stdin, a line on each stream, exit code 3.
COMMAND = """
import sys
data = sys.stdin.buffer.read() if not sys.stdin.isatty() else b""
sys.stdout.write(f"got {len(data)} bytes\\nsecond line\\n")
sys.stderr.write("a warning\\n")
sys.exit(3)
"""


class FakeDocker:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.failing: set[str] = set()  # docker commands that fail
        self.error = b"Error response from daemon: boom"  # their stderr
        self.leftovers = b""  # what `docker ps` lists
        self.state = b"true false"  # what `docker inspect` says: running, OOM-killed

    async def run(
        self, args: Sequence[str], *, stdin: bytes | None = None, timeout: float = 60
    ) -> tuple[int, bytes, bytes]:
        self.calls.append(list(args))
        if args[0] in self.failing:
            return 1, b"", self.error
        return 0, {"ps": self.leftovers, "inspect": self.state}.get(args[0], b""), b""

    async def start(self, args: Sequence[str], *, stdin: bool) -> Process:
        self.calls.append(list(args))
        pipe = asyncio.subprocess.PIPE
        return await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            COMMAND,
            stdin=pipe if stdin else asyncio.subprocess.DEVNULL,
            stdout=pipe,
            stderr=pipe,
        )


@pytest.fixture
def daemon() -> Iterator[tuple[Sandboxd, FakeDocker, SandboxdClient]]:
    """The daemon on loopback TCP in a thread of its own; production listens on a unix socket."""
    docker = FakeDocker()
    sandboxd = Sandboxd(POLICY, docker)
    loop = asyncio.new_event_loop()
    server = loop.run_until_complete(
        asyncio.start_server(sandboxd.handle, "127.0.0.1", 0, limit=MAX_REQUEST)
    )
    port = server.sockets[0].getsockname()[1]
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    yield sandboxd, docker, SandboxdClient(("127.0.0.1", port), timeout_s=10)
    loop.call_soon_threadsafe(loop.stop)
    thread.join()
    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()


def create(client: SandboxdClient, **fields: Any) -> dict[str, Any]:
    limits = {"cpus": LIMITS.cpus, "memory_mb": LIMITS.memory_mb, "pids": LIMITS.pids}
    return client.request({"op": "create", "image": IMAGE, "limits": limits} | fields)


def test_info(daemon: tuple[Sandboxd, FakeDocker, SandboxdClient]) -> None:
    _, _, client = daemon
    assert client.request({"op": "info"}) == {
        "runtime": "runsc",
        "images": ["ghcr.io/apparatica/toolchain"],
    }


def test_a_sandbox_gets_the_fixed_flags(
    daemon: tuple[Sandboxd, FakeDocker, SandboxdClient],
) -> None:
    sandboxd, docker, client = daemon
    sandbox_id = create(client)["id"]
    [args] = docker.calls
    name = args[args.index("--name") + 1]
    assert sandboxd.sandboxes[sandbox_id].container == name
    assert name not in sandbox_id  # the client never learns the container
    assert args[:2] == ["run", "-d"]
    assert "--rm" not in args  # the state of a sandbox that died is read before destroy
    assert args[4:6] == ["--label", LABEL]
    assert args[-2:] == [IMAGE, "apx-init"]
    for flag in (
        "--runtime=runsc",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--user=10001:10001",
        # runsc: the processes are limited inside gVisor, the host limit leaves room for the Sentry.
        "--ulimit=nproc=256:256",
        "--pids-limit=832",
        "--memory=2048m",
        "--memory-swap=2048m",
        "--cpus=2",
    ):
        assert flag in args


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"image": "docker.io/library/alpine"}, "not allowed"),
        ({"image": "--privileged"}, "not allowed"),
        ({"image": "ghcr.io/apparatica/toolchain-evil:1"}, "not allowed"),
        ({"limits": {"cpus": 8, "memory_mb": 2048, "pids": 256}}, "within"),
        ({"limits": {"cpus": 2, "memory_mb": 1 << 20, "pids": 256}}, "within"),
        ({"limits": {"cpus": 2, "memory_mb": 2048, "pids": True}}, "within"),
        ({"limits": {"cpus": 2, "memory_mb": "2048", "pids": 256}}, "within"),
        ({"limits": {"cpus": 2, "memory_mb": 2048}}, "must have"),
        ({"limits": {"cpus": 2, "memory_mb": 2048, "pids": 256, "privileged": 1}}, "must have"),
    ],
)
def test_create_is_refused(
    daemon: tuple[Sandboxd, FakeDocker, SandboxdClient], fields: dict[str, Any], reason: str
) -> None:
    _, docker, client = daemon
    with pytest.raises(ExecutorError, match=reason):
        create(client, **fields)
    assert docker.calls == []


def test_sandboxes_are_counted(daemon: tuple[Sandboxd, FakeDocker, SandboxdClient]) -> None:
    _, docker, client = daemon
    create(client)
    create(client)
    with pytest.raises(ExecutorError, match="too many"):
        create(client)
    assert len(docker.calls) == 2


def test_a_failed_docker_run(daemon: tuple[Sandboxd, FakeDocker, SandboxdClient]) -> None:
    sandboxd, docker, client = daemon
    docker.failing.add("run")
    with pytest.raises(ExecutorError, match="cannot create the sandbox: Error response"):
        create(client)
    assert sandboxd.sandboxes == {}


def test_exec_streams_the_command(daemon: tuple[Sandboxd, FakeDocker, SandboxdClient]) -> None:
    sandboxd, docker, client = daemon
    container = SandboxContainer(client, IMAGE, LIMITS)
    container.create()
    code, out, err = container.run(["tar", "-x", "-C", "/work/lint"], stdin=b"x" * 100_000)
    assert (code, out.replace(b"\r", b""), err) == (
        3,
        b"got 100000 bytes\nsecond line\n",
        "a warning",
    )
    name = sandboxd.sandboxes[str(container.id)].container
    # The command comes after the container name: it can never be a docker option.
    assert docker.calls[-1] == ["exec", "-i", "-w", "/work", name, "tar", "-x", "-C", "/work/lint"]

    running = container.start(["apx-run", "--privileged"], cwd="/work/sim")
    [(read, channel)] = running.streams
    chunks = []
    while chunk := read():
        chunks.append(chunk)
    assert (running.wait(), channel, running.marked) == (3, "out", True)
    assert b"".join(chunks).replace(b"\r", b"") == b"got 0 bytes\nsecond line\n"
    assert docker.calls[-1] == ["exec", "-t", "-w", "/work/sim", name, "apx-run", "--privileged"]


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"argv": "sh -c 'id'"}, "argv"),
        ({"argv": []}, "argv"),
        ({"argv": ["sh", 1]}, "argv"),
        ({"argv": ["sh", ""]}, "argv"),
        ({"argv": ["sh\0"]}, "argv"),
        ({"cwd": "/"}, "cwd"),
        ({"cwd": "/work/../etc"}, "cwd"),
        ({"cwd": "/workshop"}, "cwd"),
        ({"cwd": "/work/a b"}, "cwd"),
        ({"tty": "yes"}, "tty"),
        ({"tty": True, "stdin": ""}, "tty"),
        ({"stdin": "not base64!"}, "base64"),
        ({"id": "someone-else"}, "unknown sandbox"),
    ],
)
def test_exec_is_refused(
    daemon: tuple[Sandboxd, FakeDocker, SandboxdClient], fields: dict[str, Any], reason: str
) -> None:
    _, docker, client = daemon
    sandbox_id = create(client)["id"]
    request = {"op": "exec", "id": sandbox_id, "argv": ["true"], "cwd": "/work"} | fields
    with pytest.raises(ExecutorError, match=reason):
        client.request(request)
    assert len(docker.calls) == 1  # only the create


def test_kill_and_destroy(daemon: tuple[Sandboxd, FakeDocker, SandboxdClient]) -> None:
    sandboxd, docker, client = daemon
    container = SandboxContainer(client, IMAGE, LIMITS)
    container.create()
    name = sandboxd.sandboxes[str(container.id)].container
    sandbox_id = container.id
    container.kill_all()
    assert docker.calls[-1] == ["exec", name, "sh", "-c", "kill -KILL -1 || true"]
    container.destroy()
    assert docker.calls[-1] == ["rm", "-f", name]
    assert sandboxd.sandboxes == {}
    with pytest.raises(ExecutorError, match="unknown sandbox"):
        client.request({"op": "kill", "id": sandbox_id})


@pytest.mark.parametrize(
    ("state", "oom", "stopped"),
    [
        pytest.param(b"false true", True, False, id="killed-by-its-memory-limit"),
        pytest.param(b"false false", False, False, id="died"),
        pytest.param(b"true false", False, True, id="kill-cannot-start"),
    ],
)
def test_a_lost_sandbox(
    daemon: tuple[Sandboxd, FakeDocker, SandboxdClient], state: bytes, oom: bool, stopped: bool
) -> None:
    sandboxd, docker, client = daemon
    container = SandboxContainer(client, IMAGE, LIMITS)
    container.create()
    name = sandboxd.sandboxes[str(container.id)].container
    docker.failing.add("exec")
    docker.state = state
    with pytest.raises(SandboxLostError) as lost:
        container.kill_all()
    assert lost.value.oom is oom
    inspect = ["inspect", "--format", "{{.State.Running}} {{.State.OOMKilled}}", name]
    assert docker.calls[2:] == [inspect, ["kill", name]] if stopped else [inspect]
    container.destroy()
    assert sandboxd.sandboxes == {}


def test_a_kill_without_docker_is_refused(
    daemon: tuple[Sandboxd, FakeDocker, SandboxdClient],
) -> None:
    _, docker, client = daemon
    container = SandboxContainer(client, IMAGE, LIMITS)
    container.create()
    docker.failing |= {"exec", "inspect"}
    with pytest.raises(ExecutorError, match="cannot kill") as refused:
        container.kill_all()
    assert not isinstance(refused.value, SandboxLostError)


def test_destroy_of_a_container_that_is_gone(
    daemon: tuple[Sandboxd, FakeDocker, SandboxdClient],
) -> None:
    sandboxd, docker, client = daemon
    container = SandboxContainer(client, IMAGE, LIMITS)
    container.create()
    sandbox_id = str(container.id)
    docker.failing.add("rm")
    with pytest.raises(ExecutorError, match="cannot remove"):
        client.request({"op": "destroy", "id": sandbox_id})
    assert sandbox_id in sandboxd.sandboxes  # kept: the daemon tries again or reaps it
    docker.error = b"Error response from daemon: No such container: apx-sandbox-0"
    container.destroy()
    assert sandboxd.sandboxes == {}


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        (b"not json\n", "not JSON"),
        (b"[1, 2]\n", "not an object"),
        (b'{"op": "run"}\n', "unknown operation"),
        (b'{"op": ["create"]}\n', "unknown operation"),
    ],
)
def test_malformed_requests(
    daemon: tuple[Sandboxd, FakeDocker, SandboxdClient], line: bytes, reason: str
) -> None:
    _, _, client = daemon
    assert isinstance(client.address, tuple)
    with socket.create_connection(client.address, timeout=5) as connection:
        connection.sendall(line)
        reply = connection.makefile("rb").readline()
    assert reason.encode() in reply


def test_leftovers_and_expired_sandboxes_are_removed() -> None:
    docker = FakeDocker()
    docker.leftovers = b"c1\nc2\n"
    sandboxd = Sandboxd(POLICY, docker)
    asyncio.run(sandboxd.remove_leftovers())
    assert docker.calls == [["ps", "-aq", "--filter", f"label={LABEL}"], ["rm", "-f", "c1", "c2"]]

    sandboxd.sandboxes = {
        "old": _Sandbox("apx-sandbox-old", created=time.monotonic() - 7200),
        "new": _Sandbox("apx-sandbox-new"),
    }
    asyncio.run(sandboxd.reap())
    assert list(sandboxd.sandboxes) == ["new"]
    assert docker.calls[-1] == ["rm", "-f", "apx-sandbox-old"]


@pytest.mark.parametrize(
    ("image", "name"),
    [
        ("apparatica-toolchain:dev", "apparatica-toolchain"),
        ("ghcr.io/apparatica/toolchain:2026.10.3", "ghcr.io/apparatica/toolchain"),
        ("ghcr.io/apparatica/toolchain@sha256:abc", "ghcr.io/apparatica/toolchain"),
        ("localhost:5000/toolchain:1", "localhost:5000/toolchain"),
        ("--privileged", "--privileged"),
    ],
)
def test_repository(image: str, name: str) -> None:
    assert repository(image) == name
