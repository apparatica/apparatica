"""Executors run a `StagePlan` and stream its output (specs/07 §2, §4.3, §5).

- `LocalDockerExecutor`: a container of the toolchain image with the sandbox restrictions, one per
  submission, commands through `docker exec -t` and `apx-run` — `judge` locally and in CI.
- `HostExecutor`: plain subprocesses in a temporary directory (`judge --no-docker`): no isolation,
  for trusted code only.
- The worker's executor talks to `apx-sandboxd` instead of Docker (T1.2b).

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
from collections.abc import Callable, Iterable, Sequence
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
        self, stage_key: str, plan: StagePlan, on_line: OnLine, cancel: threading.Event
    ) -> ExecResult: ...


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


def _pump(stream: IO[bytes], lines: _Lines, events: "queue.Queue[tuple[_Lines, bytes]]") -> None:
    while chunk := os.read(stream.fileno(), 65536):
        events.put((lines, chunk))
    events.put((lines, b""))


def _run_streaming(
    argv: Sequence[str],
    streams: Callable[[subprocess.Popen[bytes]], Iterable[tuple[IO[bytes], _Lines]]],
    *,
    popen: Callable[[], subprocess.Popen[bytes]],
    deadline: float,
    budget: _Budget,
    on_line: OnLine,
    cancel: threading.Event,
    kill: Callable[[subprocess.Popen[bytes]], None],
) -> tuple[CommandResult, str | None]:
    """Run one command; returns its result and why it was killed (timeout, output, cancel)."""
    started = time.monotonic()
    process = popen()
    events: queue.Queue[tuple[_Lines, bytes]] = queue.Queue()
    readers = [
        threading.Thread(target=_pump, args=(stream, lines, events), daemon=True)
        for stream, lines in streams(process)
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
                kill(process)
        try:
            lines, chunk = events.get(timeout=_POLL_S)
        except queue.Empty:
            continue
        if chunk:
            emit(lines.feed(chunk))
        else:
            open_streams -= 1
            emit(lines.flush())
    exit_code = process.wait()
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
        self, stage_key: str, plan: StagePlan, on_line: OnLine, cancel: threading.Event
    ) -> ExecResult:
        workdir = self.root / check_relative(stage_key)
        if workdir.exists():
            shutil.rmtree(workdir)
        workdir.mkdir(parents=True)
        for name, content in plan.inputs.items():
            target = workdir / check_relative(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

        def run_one(
            argv: Sequence[str], deadline: float, budget: _Budget
        ) -> tuple[CommandResult, str | None]:
            def popen() -> subprocess.Popen[bytes]:
                try:
                    return subprocess.Popen(
                        argv,
                        cwd=workdir,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        start_new_session=sys.platform != "win32",
                    )
                except OSError as error:
                    raise ExecutorError(f"cannot start {argv[0]}: {error}") from error

            def streams(
                process: subprocess.Popen[bytes],
            ) -> list[tuple[IO[bytes], _Lines]]:
                assert process.stdout is not None
                assert process.stderr is not None
                return [
                    (process.stdout, _Lines("out", marked=False)),
                    (process.stderr, _Lines("err", marked=False)),
                ]

            return _run_streaming(
                argv,
                streams,
                popen=popen,
                deadline=deadline,
                budget=budget,
                on_line=on_line,
                cancel=cancel,
                kill=_kill_host,
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


def sandbox_flags(limits: SandboxLimits) -> list[str]:
    """`docker run` flags of the sandbox container (specs/07 §5.1)."""
    return [
        "--network=none",
        "--read-only",
        f"--tmpfs=/work:exec,size=512m,uid={SANDBOX_UID},gid={SANDBOX_UID}",
        "--tmpfs=/tmp:size=64m",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        f"--pids-limit={limits.pids}",
        f"--memory={limits.memory_mb}m",
        f"--memory-swap={limits.memory_mb}m",
        f"--cpus={limits.cpus:g}",
    ]


class LocalDockerExecutor:
    """One container of the toolchain image per submission, driven with the docker CLI."""

    def __init__(self, image: str, limits: SandboxLimits, *, runtime: str | None = None) -> None:
        self.image = image
        self.limits = limits
        self.runtime = runtime  # e.g. runsc; None: the Docker default
        self.container = f"apx-judge-{uuid.uuid4().hex[:12]}"

    def __enter__(self) -> Self:
        runtime = [f"--runtime={self.runtime}"] if self.runtime else []
        # TODO(T1.2a): PID 1 becomes apx-init from the image (S6); sleep leaves zombies behind.
        argv = ["docker", "run", "-d", "--rm", "--name", self.container, *runtime]
        argv += [*sandbox_flags(self.limits), self.image, "sleep", "infinity"]
        self._docker(argv, "start the sandbox container")
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        subprocess.run(["docker", "rm", "-f", self.container], capture_output=True, check=False)

    def run(
        self, stage_key: str, plan: StagePlan, on_line: OnLine, cancel: threading.Event
    ) -> ExecResult:
        workdir = f"/work/{check_relative(stage_key)}"
        self._exec(["mkdir", workdir], f"create {workdir}")
        self._put(workdir, plan)

        def run_one(
            argv: Sequence[str], deadline: float, budget: _Budget
        ) -> tuple[CommandResult, str | None]:
            # A TTY makes tools print line by line; apx-run keeps stderr apart (specs/07 §4.3).
            command = ["docker", "exec", "-t", "-w", workdir, self.container, "apx-run", *argv]

            def popen() -> subprocess.Popen[bytes]:
                try:
                    return subprocess.Popen(
                        command,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                    )
                except OSError as error:
                    raise ExecutorError(f"cannot run docker: {error}") from error

            def streams(process: subprocess.Popen[bytes]) -> list[tuple[IO[bytes], _Lines]]:
                assert process.stdout is not None
                return [(process.stdout, _Lines("out", marked=True))]

            return _run_streaming(
                argv,
                streams,
                popen=popen,
                deadline=deadline,
                budget=budget,
                on_line=on_line,
                cancel=cancel,
                kill=lambda _: self._kill_all(),
            )

        try:
            results, stop, budget = _run_plan(plan, run_one)
        finally:
            # Nothing a stage started survives into the next one (specs/07 §5.2).
            self._kill_all()
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
        self._exec(["tar", "-x", "-C", workdir], "upload stage inputs", stdin=archive.getvalue())

    def _collect(self, workdir: str, plan: StagePlan) -> tuple[dict[str, bytes], set[str]]:
        files, oversized = {}, set()
        for name in plan.collect:
            path = f"{workdir}/{check_relative(name)}"
            # head bounds what is read from the sandbox; one extra byte detects an oversized file.
            script = 'test -f "$1" && exec head -c "$2" "$1"'
            argv = ["sh", "-c", script, "sh", path, str(plan.collect_limit + 1)]
            result = self._exec(argv, None)
            if result.returncode != 0:
                continue
            if len(result.stdout) > plan.collect_limit:
                oversized.add(name)
            else:
                files[name] = result.stdout
        return files, oversized

    def _kill_all(self) -> None:
        """SIGKILL every process of the sandbox user; killing the exec client is not enough (S6)."""
        self._exec(["sh", "-c", "kill -KILL -1"], None)

    def _exec(
        self, argv: list[str], what: str | None, stdin: bytes | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        options = ["-i"] if stdin is not None else []
        command = ["docker", "exec", *options, self.container, *argv]
        result = self._docker(command, what, stdin=stdin)
        return result

    def _docker(
        self, argv: list[str], what: str | None, stdin: bytes | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        try:
            result = subprocess.run(argv, input=stdin, capture_output=True, check=False, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ExecutorError(f"docker failed: {error}") from error
        if what is not None and result.returncode != 0:
            message = result.stderr.decode(errors="replace").strip()
            raise ExecutorError(f"cannot {what}: {message}")
        return result
