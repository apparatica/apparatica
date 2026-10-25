"""The judge's LocalDockerExecutor against the image: what `judge run` does locally and in CI."""

import threading
from collections.abc import Iterator

import pytest

from judge.core.executor import LocalDockerExecutor
from judge.core.limits import SandboxLimits
from judge.core.stage import Command, ExecResult, StagePlan
from sandbox import IMAGE

Lines = list[tuple[str, str]]


@pytest.fixture(scope="module")
def executor() -> Iterator[LocalDockerExecutor]:
    with LocalDockerExecutor(IMAGE, SandboxLimits(cpus=2, memory_mb=2048, pids=256)) as running:
        yield running


def sh(script: str) -> Command:
    return Command(("sh", "-c", script))


def run(
    executor: LocalDockerExecutor,
    stage: str,
    *commands: Command,
    cancel: threading.Event | None = None,
    timeout_s: float = 30,
    output_limit: int = 1 << 16,
    inputs: dict[str, bytes] | None = None,
    collect: tuple[str, ...] = (),
) -> tuple[ExecResult, Lines]:
    lines: Lines = []
    plan = StagePlan(
        commands=commands,
        timeout_s=timeout_s,
        output_limit=output_limit,
        inputs=inputs or {},
        collect=collect,
        collect_limit=64,
    )
    result = executor.run(
        stage, plan, lambda ch, text: lines.append((ch, text)), cancel or threading.Event()
    )
    return result, lines


def test_streams_lines_with_channels(executor: LocalDockerExecutor) -> None:
    result, lines = run(executor, "stream", sh("echo one; echo oops >&2; printf tail"))
    assert result.ok
    assert sorted(lines) == [("err", "oops"), ("out", "one"), ("out", "tail")]


def test_inputs_and_outputs(executor: LocalDockerExecutor) -> None:
    result, _ = run(
        executor,
        "files",
        sh("cat src/in.txt src/in.txt > out.txt; head -c 100 /dev/zero > big.bin"),
        inputs={"src/in.txt": "тест".encode()},
        collect=("out.txt", "big.bin", "missing.txt"),
    )
    assert result.ok
    assert result.files == {"out.txt": "тесттест".encode()}
    assert result.oversized == frozenset({"big.bin"})


def test_exit_code_stops_the_plan(executor: LocalDockerExecutor) -> None:
    result, lines = run(executor, "exit", sh("exit 3"), sh("echo never"))
    assert [c.exit_code for c in result.commands] == [3]
    assert lines == []


def test_timeout_kills_the_command(executor: LocalDockerExecutor) -> None:
    result, _ = run(executor, "timeout", sh("sleep 60"), timeout_s=1)
    assert result.timed_out
    assert result.commands[0].exit_code is None
    assert result.commands[0].duration_s < 10


def test_output_limit_kills_the_command(executor: LocalDockerExecutor) -> None:
    result, lines = run(executor, "output", Command(("yes",)), output_limit=10_000)
    assert result.output_limited
    assert sum(len(text) + 1 for _, text in lines) <= 10_000


def test_cancellation(executor: LocalDockerExecutor) -> None:
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    result, _ = run(executor, "cancel", sh("sleep 60"), cancel=cancel)
    assert result.cancelled


def test_no_process_survives_a_stage(executor: LocalDockerExecutor) -> None:
    run(executor, "leave", sh("sleep 300 > /dev/null 2>&1 &"))
    # PID 1 is the container's own; anything else from the previous stage must be gone.
    script = "for p in /proc/[0-9]*; do tr '\\0' ' ' < $p/cmdline; echo; done"
    result, lines = run(executor, "check", sh(script))
    assert result.ok
    assert not [text for _, text in lines if text.startswith("sleep 300")]
