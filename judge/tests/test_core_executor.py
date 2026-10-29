import threading
import time
from collections.abc import Sequence
from pathlib import Path

import pytest
from core_helpers import python

from judge.core.executor import (
    ContainerExecutor,
    ExecutorError,
    HostExecutor,
    Running,
    SandboxLostError,
    check_relative,
    sandbox_flags,
)
from judge.core.limits import SandboxLimits
from judge.core.stage import Command, ExecResult, StagePlan

Lines = list[tuple[str, str]]


def run(plan: StagePlan, cancel: threading.Event | None = None) -> tuple[ExecResult, Lines]:
    lines: Lines = []
    with HostExecutor() as executor:
        result = executor.run(
            "stage", plan, lambda ch, text: lines.append((ch, text)), cancel or threading.Event()
        )
    return result, lines


def plan(*commands: Command, **options: object) -> StagePlan:
    defaults: dict[str, object] = {"timeout_s": 10.0, "output_limit": 1 << 16}
    return StagePlan(commands=commands, **(defaults | options))  # type: ignore[arg-type]


def test_streams_both_channels_and_runs_commands_in_order() -> None:
    result, lines = run(
        plan(
            python("import sys; print('one'); print('oops', file=sys.stderr)"),
            python("print('two', end='')"),  # a tail without newline is kept
        )
    )
    assert result.ok
    assert [c.exit_code for c in result.commands] == [0, 0]
    assert sorted(lines) == [("err", "oops"), ("out", "one"), ("out", "two")]
    assert "one\n" in result.output


def test_stops_at_the_first_failing_command() -> None:
    result, _ = run(plan(python("raise SystemExit(3)"), python("print('never')")))
    assert not result.ok
    assert [c.exit_code for c in result.commands] == [3]


def test_inputs_and_collected_files() -> None:
    code = "d = open('src/a.txt').read(); open('out.txt', 'w').write(d * 2)"
    result, _ = run(
        plan(
            python(code + "; open('big.bin', 'wb').write(b'x' * 100)"),
            inputs={"src/a.txt": b"ab"},
            collect=("out.txt", "missing.txt", "big.bin"),
            collect_limit=10,
        )
    )
    assert result.files == {"out.txt": b"abab"}
    assert result.oversized == frozenset({"big.bin"})


def test_timeout_kills_the_command() -> None:
    started = time.monotonic()
    result, _ = run(plan(python("import time; time.sleep(30)"), timeout_s=0.5))
    assert result.timed_out
    assert result.commands[0].exit_code is None
    assert time.monotonic() - started < 10


def test_timeout_covers_the_whole_plan() -> None:
    sleep = python("import time; time.sleep(0.4)")
    result, _ = run(plan(sleep, sleep, sleep, timeout_s=1.0))
    assert result.timed_out
    assert len(result.commands) >= 2  # the second command already runs out of time
    assert result.commands[-1].exit_code is None


def test_output_limit_kills_the_command() -> None:
    result, lines = run(plan(python("while True: print('y' * 99)"), output_limit=1000))
    assert result.output_limited
    assert result.commands[0].exit_code is None
    assert sum(len(text) + 1 for _, text in lines) <= 1000


def test_cancellation() -> None:
    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()
    result, _ = run(plan(python("import time; time.sleep(30)")), cancel)
    assert result.cancelled
    assert not result.ok


def test_missing_program_is_an_executor_error() -> None:
    with pytest.raises(ExecutorError, match="cannot start"):
        run(plan(Command(("apx-no-such-program",))))


@pytest.mark.parametrize("path", ["/etc/passwd", "../x", "a/../../x", ""])
def test_plan_paths_stay_in_the_stage_directory(path: str) -> None:
    with pytest.raises(ValueError, match="inside the stage directory"):
        check_relative(path)


def test_stage_directory_is_fresh(tmp_path: Path) -> None:
    with HostExecutor(tmp_path) as executor:
        first = plan(python("open('left.txt', 'w').write('x')"))
        executor.run("s", first, lambda *_: None, threading.Event())
        second = plan(python("import os; print(os.listdir('.'))"), collect=("left.txt",))
        result = executor.run("s", second, lambda *_: None, threading.Event())
    assert result.files == {}
    assert "[]" in result.output


def test_follow_up_run_reuses_the_directory(tmp_path: Path) -> None:
    with HostExecutor(tmp_path) as executor:
        first = plan(python("open('left.txt', 'w').write('x')"))
        executor.run("s", first, lambda *_: None, threading.Event())
        again = plan(python("pass"), collect=("left.txt",))
        result = executor.run("s", again, lambda *_: None, threading.Event(), reuse_dir=True)
    assert result.files == {"left.txt": b"x"}


def test_utf8_output_and_crlf() -> None:
    code = "import sys; sys.stdout.buffer.write('тест\\r\\n'.encode())"
    _, lines = run(plan(python(code)))
    assert lines == [("out", "тест")]


class LosingContainer:
    """A sandbox that is lost by the kill after the stage: its command prints one line and exits
    with `exit_code`, or runs until killed."""

    def __init__(self, *, oom: bool, exit_code: int | None = 0) -> None:
        self.oom = oom
        self.exit_code = exit_code
        self.calls: list[list[str]] = []
        self.killed = threading.Event()

    def run(self, argv: Sequence[str], *, stdin: bytes | None = None) -> tuple[int, bytes, str]:
        self.calls.append(list(argv))
        return 0, b"", ""

    def start(self, argv: Sequence[str], *, cwd: str) -> Running:
        chunks = [b"line\n"]

        def read() -> bytes:
            if chunks:
                return chunks.pop()
            if self.exit_code is None:
                self.killed.wait(10)
            return b""

        return Running(
            streams=[(read, "out")], wait=lambda: self.exit_code or 0, kill=self.kill_all
        )

    def kill_all(self) -> None:
        self.killed.set()
        raise SandboxLostError(oom=self.oom)


def run_in(container: LosingContainer, timeout_s: float = 10.0) -> ExecResult:
    executor = ContainerExecutor(container)
    stage = plan(Command(("sim",)), timeout_s=timeout_s, collect=("result.json",))
    return executor.run("sim", stage, lambda *_: None, threading.Event())


def test_a_sandbox_killed_by_its_memory_limit() -> None:
    container = LosingContainer(oom=True, exit_code=128)
    result = run_in(container)
    assert result.memory_exceeded
    assert not result.ok
    assert result.files == {}
    assert not [call for call in container.calls if call[0] == "sh" and "head" in call[2]]


def test_a_sandbox_lost_after_a_command_that_ended() -> None:
    with pytest.raises(SandboxLostError):
        run_in(LosingContainer(oom=False))


def test_a_sandbox_lost_after_a_timeout_keeps_the_timeout() -> None:
    """A fork bomb leaves no room for the kill: the stage still ends with its time limit."""
    result = run_in(LosingContainer(oom=False, exit_code=None), timeout_s=0.3)
    assert result.timed_out
    assert not result.memory_exceeded
    assert result.files == {}


@pytest.mark.parametrize(
    ("runtime", "expected"),
    [
        (None, ["--pids-limit=256"]),
        ("runc", ["--pids-limit=256"]),
        ("runsc", ["--pids-limit=832", "--ulimit=nproc=256:256"]),
    ],
)
def test_the_process_limit_depends_on_the_runtime(runtime: str | None, expected: list[str]) -> None:
    flags = sandbox_flags(SandboxLimits(cpus=2, memory_mb=2048, pids=256), runtime)
    assert [f for f in flags if f.startswith(("--pids-limit", "--ulimit"))] == expected
