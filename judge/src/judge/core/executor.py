"""Executors run a `StagePlan` and stream its output (specs/07 §2, §4.3, §5).

- `ContainerExecutor`: a sandbox container of the toolchain image, one per submission (specs/07
  §5.1-5.2), driven through a `Container`. `LocalDockerExecutor` drives it with the docker CLI
  (`judge` locally and in CI); the worker drives it through `apx-sandboxd`.
- `HostExecutor`: plain subprocesses in a temporary directory (`judge --no-docker`): no isolation,
  for trusted code only.

All of them enforce the plan's time and output limits, honour cancellation and kill what is left of
a stage before the next one starts.
"""

import contextlib
import io
import os
import queue
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import TracebackType
from typing import IO, Protocol, Self

from judge.core.limits import SandboxLimits
from judge.core.stage import Channel, CommandResult, ExecResult, StagePlan

OnLine = Callable[[Channel, str], None]
ERR_MARK = "\x1e"  # apx-run marks stderr lines with an ASCII record separator
_POLL_S = 0.05


class ExecutorError(Exception):
    """The platform failed (Docker unavailable, container gone): the stage gets status error."""


class Executor(Protocol):
    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def run(
        self,
        stage_key: str,
        plan: StagePlan,
        on_line: OnLine,
        cancel: threading.Event,
        *,
        reuse_dir: bool = False,
    ) -> ExecResult:
        """Run a plan in the stage directory: fresh, or as the previous run of this stage left it
        (`reuse_dir`, for follow-up runs that need its files, e.g. the built simulator)."""
        ...


def check_relative(path: str) -> PurePosixPath:
    """A plan path must stay inside the stage directory."""
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise ValueError(f"plan path {path!r} must be relative and inside the stage directory")
    return pure


class _Budget:
    """Output limit and console capture shared by the commands of one plan."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0
        self.exceeded = False
        self.captured = io.StringIO()

    def take(self, size: int) -> bool:
        self.used += size
        self.exceeded = self.exceeded or self.used > self.limit
        return not self.exceeded


class _Lines:
    """Splits a byte stream into lines; a tail without newline is flushed at the end."""

    def __init__(self, channel: Channel, marked: bool) -> None:
        self.channel = channel
        self.marked = marked  # stderr lines carry ERR_MARK (apx-run under a TTY)
        self._pending = b""

    def feed(self, data: bytes) -> list[tuple[Channel, str]]:
        *lines, self._pending = (self._pending + data).split(b"\n")
        return [self._decode(line) for line in lines]

    def flush(self) -> list[tuple[Channel, str]]:
        tail, self._pending = self._pending, b""
        return [self._decode(tail)] if tail else []

    def _decode(self, line: bytes) -> tuple[Channel, str]:
        text = line.decode("utf-8", errors="replace").removesuffix("\r")
        if self.marked and text.startswith(ERR_MARK):
            return "err", text[1:]
        return self.channel, text


Read = Callable[[], bytes]  # the next chunk of a stream; b"" at its end


@dataclass(frozen=True)
class Running:
    """A started command: its output streams, its exit code, how to stop it."""

    streams: Sequence[tuple[Read, Channel]]
    wait: Callable[[], int]  # raises ExecutorError when the platform lost the command
    kill: Callable[[], None]
    marked: bool = False  # stderr comes in the first stream, marked by apx-run


def _pump(read: Read, lines: _Lines, events: "queue.Queue[tuple[_Lines, bytes]]") -> None:
    try:
        while chunk := read():
            events.put((lines, chunk))
    finally:  # a failed read ends the stream too; wait() reports the failure
        events.put((lines, b""))


def _run_streaming(
    argv: Sequence[str],
    start: Callable[[], Running],
    *,
    deadline: float,
    budget: _Budget,
    on_line: OnLine,
    cancel: threading.Event,
) -> tuple[CommandResult, str | None]:
    """Run one command; returns its result and why it was killed (timeout, output, cancel)."""
    started = time.monotonic()
    running = start()
    events: queue.Queue[tuple[_Lines, bytes]] = queue.Queue()
    readers = [
        threading.Thread(
            target=_pump, args=(read, _Lines(channel, running.marked), events), daemon=True
        )
        for read, channel in running.streams
    ]
    for reader in readers:
        reader.start()
    open_streams, stop = len(readers), None

    def emit(pairs: list[tuple[Channel, str]]) -> None:
        for channel, text in pairs:
            if budget.take(len(text.encode()) + 1):
                budget.captured.write(text + "\n")
                on_line(channel, text)

    while open_streams:
        if stop is None:
            if cancel.is_set():
                stop = "cancelled"
            elif time.monotonic() > deadline:
                stop = "timeout"
            elif budget.exceeded:
                stop = "output"
            if stop is not None:
                running.kill()
        try:
            lines, chunk = events.get(timeout=_POLL_S)
        except queue.Empty:
            continue
        if chunk:
            emit(lines.feed(chunk))
        else:
            open_streams -= 1
            emit(lines.flush())
    exit_code = running.wait()
    if stop is None and budget.exceeded:
        stop = "output"
    duration = time.monotonic() - started
    return CommandResult(tuple(argv), None if stop else exit_code, duration), stop


def _run_plan(
    plan: StagePlan,
    run_one: Callable[[Sequence[str], float, _Budget], tuple[CommandResult, str | None]],
) -> tuple[list[CommandResult], str | None, _Budget]:
    deadline = time.monotonic() + plan.timeout_s
    budget = _Budget(plan.output_limit)
    results: list[CommandResult] = []
    for command in plan.commands:
        result, stop = run_one(command.argv, deadline, budget)
        results.append(result)
        if stop is not None or result.exit_code != 0:
            return results, stop, budget
    return results, None, budget


def _exec_result(
    results: list[CommandResult],
    stop: str | None,
    budget: _Budget,
    files: dict[str, bytes],
    oversized: set[str],
) -> ExecResult:
    return ExecResult(
        commands=tuple(results),
        output=budget.captured.getvalue(),
        timed_out=stop == "timeout",
        output_limited=stop == "output",
        cancelled=stop == "cancelled",
        files=files,
        oversized=frozenset(oversized),
    )


def _read_pipe(stream: IO[bytes] | None) -> Read:
    assert stream is not None
    fd = stream.fileno()
    return lambda: os.read(fd, 65536)


class HostExecutor:
    """Runs commands on the host in a temporary directory per stage. Not a sandbox."""

    def __init__(self, root: Path | None = None) -> None:
        self._root_arg = root
        self._tmp: tempfile.TemporaryDirectory[str] | None = None
        self.root = root or Path()

    def __enter__(self) -> Self:
        if self._root_arg is None:
            self._tmp = tempfile.TemporaryDirectory(prefix="apx-judge-")
            self.root = Path(self._tmp.name)
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()

    def run(
        self,
        stage_key: str,
        plan: StagePlan,
        on_line: OnLine,
        cancel: threading.Event,
        *,
        reuse_dir: bool = False,
    ) -> ExecResult:
        workdir = self.root / check_relative(stage_key)
        if workdir.exists() and not reuse_dir:
            shutil.rmtree(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        for name, content in plan.inputs.items():
            target = workdir / check_relative(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

        def run_one(
            argv: Sequence[str], deadline: float, budget: _Budget
        ) -> tuple[CommandResult, str | None]:
            def start() -> Running:
                try:
                    process = subprocess.Popen(
                        argv,
                        cwd=workdir,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        start_new_session=sys.platform != "win32",
                    )
                except OSError as error:
                    raise ExecutorError(f"cannot start {argv[0]}: {error}") from error
                return Running(
                    streams=[
                        (_read_pipe(process.stdout), "out"),
                        (_read_pipe(process.stderr), "err"),
                    ],
                    wait=process.wait,
                    kill=lambda: _kill_host(process),
                )

            return _run_streaming(
                argv, start, deadline=deadline, budget=budget, on_line=on_line, cancel=cancel
            )

        results, stop, budget = _run_plan(plan, run_one)
        files, oversized = {}, set()
        for name in plan.collect:
            path = workdir / check_relative(name)
            if not path.is_file():
                continue
            if path.stat().st_size > plan.collect_limit:
                oversized.add(name)
            else:
                files[name] = path.read_bytes()
        return _exec_result(results, stop, budget, files, oversized)


def _kill_host(process: subprocess.Popen[bytes]) -> None:
    if sys.platform == "win32":
        process.kill()
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)


SANDBOX_UID = 10001
# PID 1 of the sandbox container: it reaps orphans and survives `kill -KILL -1` (S6).
SANDBOX_INIT = ("apx-init",)
# Every process of the sandbox user but PID 1; nothing left to kill is not an error (no /bin/kill
# in the image: the shell builtin, S6).
KILL_ALL = ("sh", "-c", "kill -KILL -1 || true")


def sandbox_flags(limits: SandboxLimits) -> list[str]:
    """`docker run` flags of the sandbox container (specs/07 §5.1), without the runtime."""
    return [
        "--network=none",
        "--read-only",
        f"--tmpfs=/work:exec,size=512m,uid={SANDBOX_UID},gid={SANDBOX_UID}",
        "--tmpfs=/tmp:size=64m",
        f"--user={SANDBOX_UID}:{SANDBOX_UID}",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        f"--pids-limit={limits.pids}",
        f"--memory={limits.memory_mb}m",
        f"--memory-swap={limits.memory_mb}m",
        f"--cpus={limits.cpus:g}",
    ]


class Container(Protocol):
    """A running sandbox container of the toolchain image (specs/07 §5.1)."""

    def run(self, argv: Sequence[str], *, stdin: bytes | None = None) -> tuple[int, bytes, str]:
        """A short command without a TTY: exit code, stdout (binary-safe), stderr text."""
        ...

    def start(self, argv: Sequence[str], *, cwd: str) -> Running:
        """A stage command with a TTY: tools print line by line, apx-run marks stderr."""
        ...

    def kill_all(self) -> None:
        """SIGKILL every process of the sandbox user; killing the exec client is not enough (S6)."""
        ...


class ContainerExecutor:
    """Runs the plans of one submission in its container: each stage in a fresh /work/<stage>
    (specs/07 §5.2), inputs as a tar stream, outputs read back with a size bound."""

    def __init__(self, container: Container) -> None:
        self.container = container

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        pass

    def run(
        self,
        stage_key: str,
        plan: StagePlan,
        on_line: OnLine,
        cancel: threading.Event,
        *,
        reuse_dir: bool = False,
    ) -> ExecResult:
        workdir = f"/work/{check_relative(stage_key)}"
        prepare = 'mkdir -p "$1"' if reuse_dir else 'rm -rf "$1" && mkdir "$1"'
        self._check(["sh", "-c", prepare, "sh", workdir], f"prepare {workdir}")
        self._put(workdir, plan)

        def run_one(
            argv: Sequence[str], deadline: float, budget: _Budget
        ) -> tuple[CommandResult, str | None]:
            command = ["apx-run", *argv]  # keeps stderr apart under the TTY (specs/07 §4.3)
            return _run_streaming(
                argv,
                lambda: self.container.start(command, cwd=workdir),
                deadline=deadline,
                budget=budget,
                on_line=on_line,
                cancel=cancel,
            )

        try:
            results, stop, budget = _run_plan(plan, run_one)
        finally:
            # Nothing a stage started survives into the next one (specs/07 §5.2).
            self.container.kill_all()
        files, oversized = self._collect(workdir, plan)
        return _exec_result(results, stop, budget, files, oversized)

    def _put(self, workdir: str, plan: StagePlan) -> None:
        """Upload inputs as a tar stream: `docker cp` cannot write into the tmpfs (S2)."""
        if not plan.inputs:
            return
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as tar:
            for name, content in plan.inputs.items():
                info = tarfile.TarInfo(str(check_relative(name)))
                info.size, info.mode, info.mtime = len(content), 0o644, 0
                tar.addfile(info, io.BytesIO(content))
        self._check(["tar", "-x", "-C", workdir], "upload stage inputs", stdin=archive.getvalue())

    def _collect(self, workdir: str, plan: StagePlan) -> tuple[dict[str, bytes], set[str]]:
        files, oversized = {}, set()
        for name in plan.collect:
            path = f"{workdir}/{check_relative(name)}"
            # head bounds what is read from the sandbox; one extra byte detects an oversized file.
            script = 'test -f "$1" && exec head -c "$2" "$1"'
            code, data, _ = self.container.run(
                ["sh", "-c", script, "sh", path, str(plan.collect_limit + 1)]
            )
            if code != 0:
                continue
            if len(data) > plan.collect_limit:
                oversized.add(name)
            else:
                files[name] = data
        return files, oversized

    def _check(self, argv: list[str], what: str, stdin: bytes | None = None) -> None:
        code, _, stderr = self.container.run(argv, stdin=stdin)
        if code != 0:
            raise ExecutorError(f"cannot {what}: {stderr.strip()}")


class DockerContainer:
    """A sandbox container driven with the docker CLI."""

    def __init__(self, image: str, limits: SandboxLimits, *, runtime: str | None = None) -> None:
        self.image = image
        self.limits = limits
        self.runtime = runtime  # e.g. runsc; None: the Docker default
        self.name = f"apx-judge-{uuid.uuid4().hex[:12]}"

    def create(self) -> None:
        runtime = [f"--runtime={self.runtime}"] if self.runtime else []
        argv = ["docker", "run", "-d", "--rm", "--name", self.name, *runtime]
        argv += [*sandbox_flags(self.limits), self.image, *SANDBOX_INIT]
        result = self._docker(argv)
        if result.returncode != 0:
            message = result.stderr.decode(errors="replace").strip()
            raise ExecutorError(f"cannot start the sandbox container: {message}")

    def destroy(self) -> None:
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True, check=False)

    def run(self, argv: Sequence[str], *, stdin: bytes | None = None) -> tuple[int, bytes, str]:
        options = ["-i"] if stdin is not None else []
        result = self._docker(["docker", "exec", *options, self.name, *argv], stdin=stdin)
        return result.returncode, result.stdout, result.stderr.decode(errors="replace")

    def start(self, argv: Sequence[str], *, cwd: str) -> Running:
        command = ["docker", "exec", "-t", "-w", cwd, self.name, *argv]
        try:
            process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
        except OSError as error:
            raise ExecutorError(f"cannot run docker: {error}") from error
        return Running(
            streams=[(_read_pipe(process.stdout), "out")],
            wait=process.wait,
            kill=self.kill_all,
            marked=True,
        )

    def kill_all(self) -> None:
        self._docker(["docker", "exec", self.name, *KILL_ALL])

    def _docker(
        self, argv: list[str], stdin: bytes | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        try:
            return subprocess.run(argv, input=stdin, capture_output=True, check=False, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ExecutorError(f"docker failed: {error}") from error


class LocalDockerExecutor(ContainerExecutor):
    """One container of the toolchain image per submission, driven with the docker CLI."""

    container: DockerContainer

    def __init__(self, image: str, limits: SandboxLimits, *, runtime: str | None = None) -> None:
        super().__init__(DockerContainer(image, limits, runtime=runtime))

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
