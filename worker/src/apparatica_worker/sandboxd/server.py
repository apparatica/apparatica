"""The apx-sandboxd daemon (see the package docstring for the protocol)."""

import asyncio
import base64
import binascii
import contextlib
import json
import os
import re
import sys
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

import structlog
from pydantic import Field, PositiveFloat, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict

from apparatica_worker.logging import configure_logging
from judge.core.executor import KILL_ALL, SANDBOX_INIT, sandbox_flags
from judge.core.limits import SandboxLimits

log = structlog.get_logger(__name__)

LABEL = "apparatica.sandbox"  # every container of the daemon carries it
MAX_REQUEST = 64 << 20  # a request line: the stage inputs travel in it
STDERR_TAIL = 4096
CREATE_TIMEOUT_S = 300  # includes pulling the image
DOCKER_TIMEOUT_S = 60
REAP_INTERVAL_S = 30
CWD = re.compile(r"^/work(/[A-Za-z0-9._-]+)*$")


class SandboxdSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APX_SANDBOXD_", extra="ignore", frozen=True)

    socket: Path = Path("/run/apx-sandboxd/sandboxd.sock")
    socket_group: str | None = Field(
        default=None, description="Group of the orchestrator user: it may connect, others not"
    )
    runtime: Literal["runsc", "runc"] = Field(
        default="runsc", description="runc only for development without gVisor (ADR-0003)"
    )
    images: list[str] = Field(
        default=["ghcr.io/apparatica/toolchain", "apparatica-toolchain"],
        description="Repositories of the toolchain images that may be started, JSON",
    )
    max_cpus: PositiveFloat = 4
    max_memory_mb: PositiveInt = 8192
    max_pids: PositiveInt = 256
    max_sandboxes: PositiveInt = 8
    max_lifetime_s: PositiveFloat = Field(
        default=3600, description="A sandbox older than this is destroyed: its orchestrator is gone"
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "console"


class RejectedError(Exception):
    """The request is refused; the reason goes back to the client."""


class Process(Protocol):
    stdin: asyncio.StreamWriter | None
    stdout: asyncio.StreamReader | None
    stderr: asyncio.StreamReader | None

    async def wait(self) -> int: ...

    def kill(self) -> None: ...


class Docker(Protocol):
    async def run(
        self, args: Sequence[str], *, stdin: bytes | None = None, timeout: float = DOCKER_TIMEOUT_S
    ) -> tuple[int, bytes, bytes]: ...

    async def start(self, args: Sequence[str], *, stdin: bool) -> Process: ...


class DockerCli:
    """The docker CLI: every argument after the container name is the command, never an option."""

    async def run(
        self, args: Sequence[str], *, stdin: bytes | None = None, timeout: float = DOCKER_TIMEOUT_S
    ) -> tuple[int, bytes, bytes]:
        process = await self._spawn(args, stdin=stdin is not None)
        try:
            out, err = await asyncio.wait_for(process.communicate(stdin), timeout)
        except TimeoutError:
            process.kill()
            await process.wait()
            return -1, b"", b"docker did not answer in time"
        return process.returncode or 0, out, err

    async def start(self, args: Sequence[str], *, stdin: bool) -> Process:
        return await self._spawn(args, stdin=stdin)

    async def _spawn(self, args: Sequence[str], *, stdin: bool) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            "docker",
            *args,
            stdin=asyncio.subprocess.PIPE if stdin else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )


@dataclass(frozen=True)
class Policy:
    runtime: str
    images: frozenset[str]
    ceiling: SandboxLimits
    max_sandboxes: int
    max_lifetime_s: float

    @classmethod
    def from_settings(cls, settings: SandboxdSettings) -> "Policy":
        return cls(
            runtime=settings.runtime,
            images=frozenset(settings.images),
            ceiling=SandboxLimits(settings.max_cpus, settings.max_memory_mb, settings.max_pids),
            max_sandboxes=settings.max_sandboxes,
            max_lifetime_s=settings.max_lifetime_s,
        )


@dataclass
class _Sandbox:
    container: str
    created: float = field(default_factory=time.monotonic)


def repository(image: str) -> str:
    """`registry/name` of `registry/name:tag` or `registry/name@sha256:...`."""
    name = image.split("@", 1)[0]
    path, _, last = name.rpartition("/")
    return f"{path}/{last.split(':', 1)[0]}" if path else last.split(":", 1)[0]


Send = Callable[[dict[str, Any]], Awaitable[None]]


class Sandboxd:
    def __init__(self, policy: Policy, docker: Docker) -> None:
        self.policy = policy
        self.docker = docker
        self.sandboxes: dict[str, _Sandbox] = {}

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        async def send(message: dict[str, Any]) -> None:
            writer.write(json.dumps(message).encode() + b"\n")
            await writer.drain()

        try:
            request = await self._request(reader)
            op = request.get("op")
            operation = {
                "info": self._info,
                "create": self._create,
                "exec": self._exec,
                "kill": self._kill,
                "destroy": self._destroy,
            }.get(op if isinstance(op, str) else "")
            if operation is None:
                raise RejectedError(f"unknown operation {op!r}")
            await operation(request, send)
        except RejectedError as error:
            log.warning("request refused", reason=str(error))
            with contextlib.suppress(ConnectionError):
                await send({"error": str(error)})
        except ConnectionError:
            pass  # the client is gone; an exec it left was stopped
        finally:
            writer.close()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()

    async def _request(self, reader: asyncio.StreamReader) -> dict[str, Any]:
        try:
            line = await reader.readuntil(b"\n")
        except asyncio.LimitOverrunError:
            raise RejectedError("the request is too large") from None
        except asyncio.IncompleteReadError:
            raise RejectedError("no request") from None
        try:
            request = json.loads(line)
        except ValueError:
            raise RejectedError("the request is not JSON") from None
        if not isinstance(request, dict):
            raise RejectedError("the request is not an object")
        return request

    async def _info(self, request: dict[str, Any], send: Send) -> None:
        await send({"runtime": self.policy.runtime, "images": sorted(self.policy.images)})

    async def _create(self, request: dict[str, Any], send: Send) -> None:
        image = request.get("image")
        if not isinstance(image, str) or repository(image) not in self.policy.images:
            raise RejectedError(f"image {image!r} is not allowed")
        limits = self._limits(request.get("limits"))
        if len(self.sandboxes) >= self.policy.max_sandboxes:
            raise RejectedError("too many sandboxes")
        name = f"apx-sandbox-{uuid.uuid4().hex[:12]}"
        args = ["run", "-d", "--rm", "--name", name, "--label", LABEL]
        args += [f"--runtime={self.policy.runtime}", *sandbox_flags(limits), image, *SANDBOX_INIT]
        code, _, err = await self.docker.run(args, timeout=CREATE_TIMEOUT_S)
        if code != 0:
            raise RejectedError(f"cannot create the sandbox: {_tail(err)}")
        sandbox_id = uuid.uuid4().hex
        self.sandboxes[sandbox_id] = _Sandbox(name)
        log.info("sandbox created", sandbox=sandbox_id, container=name, image=image)
        await send({"id": sandbox_id})

    def _limits(self, value: object) -> SandboxLimits:
        if not isinstance(value, dict) or set(value) != {"cpus", "memory_mb", "pids"}:
            raise RejectedError("limits must have cpus, memory_mb and pids")
        cpus, memory, pids = value["cpus"], value["memory_mb"], value["pids"]
        ceiling = self.policy.ceiling
        numbers = (
            isinstance(cpus, (int, float))
            and not isinstance(cpus, bool)
            and 0 < cpus <= ceiling.cpus
            and _whole(memory, ceiling.memory_mb)
            and _whole(pids, ceiling.pids)
        )
        if not numbers:
            raise RejectedError(f"limits must be positive and within {ceiling}")
        return SandboxLimits(float(cpus), int(memory), int(pids))

    def _container(self, request: dict[str, Any]) -> str:
        sandbox = self.sandboxes.get(str(request.get("id")))
        if sandbox is None:
            raise RejectedError("unknown sandbox")
        return sandbox.container

    async def _exec(self, request: dict[str, Any], send: Send) -> None:
        container = self._container(request)
        argv, cwd = request.get("argv"), request.get("cwd", "/work")
        tty, stdin = request.get("tty", False), request.get("stdin")
        if not (
            isinstance(argv, list)
            and argv
            and all(isinstance(a, str) and a and "\0" not in a for a in argv)
        ):
            raise RejectedError("argv must be a non-empty list of non-empty strings")
        if not isinstance(cwd, str) or not CWD.match(cwd) or ".." in cwd.split("/"):
            raise RejectedError("cwd must be inside /work")
        if not isinstance(tty, bool) or (tty and stdin is not None):
            raise RejectedError("tty is a boolean and excludes stdin")
        data = None
        if stdin is not None:
            try:
                data = base64.b64decode(str(stdin), validate=True)
            except binascii.Error:
                raise RejectedError("stdin must be base64") from None
        # Everything after the container name is the command, never docker options.
        options = ["-t"] if tty else ["-i"] if data is not None else []
        process = await self.docker.start(
            ["exec", *options, "-w", cwd, container, *argv], stdin=data is not None
        )
        await self._stream(process, data, send)

    async def _stream(self, process: Process, data: bytes | None, send: Send) -> None:
        assert process.stdout is not None
        assert process.stderr is not None
        stderr = asyncio.create_task(_read_tail(process.stderr))
        try:
            if data is not None:
                assert process.stdin is not None
                process.stdin.write(data)
                await process.stdin.drain()
                process.stdin.close()
            while chunk := await process.stdout.read(65536):
                await send({"out": base64.b64encode(chunk).decode()})
            code = await process.wait()
            await send({"exit": code, "stderr": _tail(await stderr)})
        except ConnectionError:
            # The client is gone: stop following the command. What it started in the sandbox
            # dies with the next kill or destroy, not with the docker client (S6).
            process.kill()
            await process.wait()
            raise
        finally:
            stderr.cancel()

    async def _kill(self, request: dict[str, Any], send: Send) -> None:
        container = self._container(request)
        code, _, err = await self.docker.run(["exec", container, *KILL_ALL])
        if code != 0:
            raise RejectedError(f"cannot kill: {_tail(err)}")
        await send({"ok": True})

    async def _destroy(self, request: dict[str, Any], send: Send) -> None:
        sandbox_id = str(request.get("id"))
        container = self._container(request)
        await self._remove(container)
        self.sandboxes.pop(sandbox_id, None)
        log.info("sandbox destroyed", sandbox=sandbox_id, container=container)
        await send({"ok": True})

    async def _remove(self, *containers: str) -> None:
        code, _, err = await self.docker.run(["rm", "-f", *containers])
        if code != 0:
            raise RejectedError(f"cannot remove: {_tail(err)}")

    async def remove_leftovers(self) -> None:
        """Containers of an earlier run of the daemon: nobody can reach them any more."""
        code, out, err = await self.docker.run(["ps", "-aq", "--filter", f"label={LABEL}"])
        if code != 0:
            raise RuntimeError(f"docker is unavailable: {_tail(err)}")
        if leftovers := out.decode().split():
            await self._remove(*leftovers)
            log.warning("leftover sandboxes removed", count=len(leftovers))

    async def reap(self) -> None:
        """Destroy sandboxes older than the lifetime: their orchestrator died before destroy."""
        now = time.monotonic()
        for sandbox_id, sandbox in list(self.sandboxes.items()):
            if now - sandbox.created > self.policy.max_lifetime_s:
                with contextlib.suppress(RejectedError):
                    await self._remove(sandbox.container)
                self.sandboxes.pop(sandbox_id, None)
                log.warning("sandbox expired", sandbox=sandbox_id, container=sandbox.container)


def _whole(value: object, ceiling: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= ceiling


def _tail(data: bytes) -> str:
    return data[-STDERR_TAIL:].decode(errors="replace").strip()


async def _read_tail(stream: asyncio.StreamReader) -> bytes:
    tail = b""
    while chunk := await stream.read(65536):
        tail = (tail + chunk)[-STDERR_TAIL:]
    return tail


async def serve(settings: SandboxdSettings, docker: Docker | None = None) -> None:
    if sys.platform == "win32":
        raise RuntimeError("apx-sandboxd listens on a unix socket")
    sandboxd = Sandboxd(Policy.from_settings(settings), docker or DockerCli())
    await sandboxd.remove_leftovers()
    path = settings.socket
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    server = await asyncio.start_unix_server(sandboxd.handle, path, limit=MAX_REQUEST)
    os.chmod(path, 0o660)  # the orchestrator's group, not the docker group (S6)
    if settings.socket_group is not None:
        import grp

        os.chown(path, -1, grp.getgrnam(settings.socket_group).gr_gid)
    log.info("apx-sandboxd started", socket=str(path), runtime=settings.runtime)
    async with server:
        while True:
            await asyncio.sleep(REAP_INTERVAL_S)
            await sandboxd.reap()


def main() -> int:
    settings = SandboxdSettings()
    configure_logging(settings.log_level, settings.log_format)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(serve(settings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
