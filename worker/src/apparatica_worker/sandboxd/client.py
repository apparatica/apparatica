"""The orchestrator's side of apx-sandboxd: `SandboxExecutor` runs the plans of a submission in a
sandbox the daemon creates (the same `ContainerExecutor` as `judge run`, without the docker CLI)."""

import base64
import json
import socket
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from types import TracebackType
from typing import IO, Any, Self

from judge.core.executor import ContainerExecutor, ExecutorError, Running, SandboxLostError
from judge.core.limits import SandboxLimits

# A unix socket path; (host, port) only for tests on systems without unix sockets.
Address = str | tuple[str, int]


class SandboxdClient:
    def __init__(self, address: Address, *, timeout_s: float | None = 300) -> None:
        self.address = address
        self.timeout_s = timeout_s  # per read, None: no limit; `create` may pull the image

    def request(self, message: dict[str, Any]) -> dict[str, Any]:
        """One request with one reply; a refusal raises ExecutorError."""
        with self.connect(message) as replies:
            return _reply(replies)

    @contextmanager
    def connect(self, message: dict[str, Any]) -> Iterator[IO[bytes]]:
        """Send a request and yield its stream of reply lines."""
        try:
            if isinstance(self.address, str):
                if sys.platform == "win32":
                    raise OSError("no unix sockets on Windows: use a (host, port) address")
                connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                connection.settimeout(self.timeout_s)
                connection.connect(self.address)
            else:
                connection = socket.create_connection(self.address, timeout=self.timeout_s)
        except OSError as error:
            raise ExecutorError(f"apx-sandboxd is unavailable: {error}") from error
        with connection, connection.makefile("rb") as replies:
            try:
                connection.sendall(json.dumps(message).encode() + b"\n")
            except OSError as error:
                raise ExecutorError(f"apx-sandboxd: {error}") from error
            yield replies


def _reply(replies: IO[bytes]) -> dict[str, Any]:
    try:
        line = replies.readline()
    except OSError as error:
        raise ExecutorError(f"apx-sandboxd: {error}") from error
    if not line:
        raise ExecutorError("apx-sandboxd closed the connection")
    reply: dict[str, Any] = json.loads(line)
    if "error" in reply:
        raise ExecutorError(f"apx-sandboxd: {reply['error']}")
    return reply


class SandboxContainer:
    """A sandbox of apx-sandboxd as a `judge.core.executor.Container`."""

    def __init__(self, client: SandboxdClient, image: str, limits: SandboxLimits) -> None:
        self.client = client
        self.image = image
        self.limits = limits
        self.id: str | None = None

    def create(self) -> None:
        limits = {
            "cpus": self.limits.cpus,
            "memory_mb": self.limits.memory_mb,
            "pids": self.limits.pids,
        }
        reply = self.client.request({"op": "create", "image": self.image, "limits": limits})
        self.id = str(reply["id"])

    def destroy(self) -> None:
        if self.id is not None:
            self.client.request({"op": "destroy", "id": self.id})
            self.id = None

    def run(self, argv: Sequence[str], *, stdin: bytes | None = None) -> tuple[int, bytes, str]:
        message = self._exec(argv, "/work", tty=False)
        if stdin is not None:
            message["stdin"] = base64.b64encode(stdin).decode()
        output = bytearray()
        with self.client.connect(message) as replies:
            while True:
                reply = _reply(replies)
                if "out" in reply:
                    output += base64.b64decode(reply["out"])
                else:
                    return int(reply["exit"]), bytes(output), str(reply.get("stderr", ""))

    def start(self, argv: Sequence[str], *, cwd: str) -> Running:
        stream = _Stream(self.client, self._exec(argv, cwd, tty=True))
        return Running(
            streams=[(stream.read, "out")], wait=stream.wait, kill=self.kill_all, marked=True
        )

    def kill_all(self) -> None:
        reply = self.client.request({"op": "kill", "id": self._id()})
        if reply.get("lost"):
            raise SandboxLostError(oom=bool(reply.get("oom")))

    def _exec(self, argv: Sequence[str], cwd: str, *, tty: bool) -> dict[str, Any]:
        return {"op": "exec", "id": self._id(), "argv": list(argv), "cwd": cwd, "tty": tty}

    def _id(self) -> str:
        if self.id is None:
            raise ExecutorError("the sandbox is not created")
        return self.id


class _Stream:
    """The output of a stage command as it comes from the daemon; the exit code ends it."""

    def __init__(self, client: SandboxdClient, message: dict[str, Any]) -> None:
        # No read timeout: a silent stage (a C++ build) is legal, the plan deadline kills it.
        self._connection = SandboxdClient(client.address, timeout_s=None).connect(message)
        self._replies = self._connection.__enter__()
        self._exit: int | None = None
        self._error: str | None = None

    def read(self) -> bytes:
        if self._exit is not None or self._error is not None:
            return b""
        try:
            reply = _reply(self._replies)
        except (ExecutorError, ValueError) as error:
            self._error = str(error)
            return b""
        if "out" in reply:
            return base64.b64decode(reply["out"]) or self.read()
        self._exit = int(reply["exit"])
        return b""

    def wait(self) -> int:
        self._connection.__exit__(None, None, None)
        if self._exit is None:
            raise ExecutorError(self._error or "apx-sandboxd: the command ended without an exit")
        return self._exit


class SandboxExecutor(ContainerExecutor):
    """The worker's executor: one sandbox of apx-sandboxd per submission."""

    container: SandboxContainer

    def __init__(self, client: SandboxdClient, image: str, limits: SandboxLimits) -> None:
        super().__init__(SandboxContainer(client, image, limits))

    def __enter__(self) -> Self:
        self.container.create()
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.container.destroy()
