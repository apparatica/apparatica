"""SandboxExecutor through a real apx-sandboxd, Docker and the toolchain image: the behaviour of
`judge run`'s LocalDockerExecutor (toolchain/tests/test_executor.py) plus PID 1 (S6).

Marked `image`: run by `just toolchain-test` after `just toolchain-build`.
"""

import asyncio
import os
import subprocess
import threading
from collections.abc import Iterator

import pytest

from apparatica_worker.sandboxd.client import SandboxdClient, SandboxExecutor
from apparatica_worker.sandboxd.server import (
    LABEL,
    MAX_REQUEST,
    DockerCli,
    Policy,
    Sandboxd,
    repository,
)
from judge.core.executor import ExecutorError
from judge.core.limits import SandboxLimits
from judge.core.stage import Command, ExecResult, StagePlan

pytestmark = pytest.mark.image

IMAGE = os.environ.get("TOOLCHAIN_IMAGE", "apparatica-toolchain:dev")
RUNTIME = os.environ.get("JUDGE_SANDBOX_RUNTIME", "runc")  # runsc on the worker hosts
LIMITS = SandboxLimits(cpus=2, memory_mb=2048, pids=256)
# Every process of the container: its state letter and command line (no ps in the image).
PROCESSES = (
    "for p in /proc/[0-9]*; do"
    ' while read -r key state rest; do [ "$key" = State: ] && printf "%s " "$state";'
    " done < $p/status;"
    " tr '\\0' ' ' < $p/cmdline; echo;"
    " done"
)

Lines = list[tuple[str, str]]


@pytest.fixture(scope="module")
def sandboxd() -> Iterator[tuple[Sandboxd, SandboxdClient]]:
    """The daemon on loopback TCP (no unix sockets on Windows); production listens on a socket."""
    policy = Policy(
        runtime=RUNTIME,
        images=frozenset({repository(IMAGE)}),
        ceiling=LIMITS,
        max_sandboxes=4,
        max_lifetime_s=3600,
    )
    daemon = Sandboxd(policy, DockerCli())
    loop = asyncio.new_event_loop()
    server = loop.run_until_complete(
        asyncio.start_server(daemon.handle, "127.0.0.1", 0, limit=MAX_REQUEST)
    )
    port = server.sockets[0].getsockname()[1]
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    yield daemon, SandboxdClient(("127.0.0.1", port))
    loop.call_soon_threadsafe(loop.stop)
    thread.join()
    server.close()
    loop.close()


@pytest.fixture(scope="module")
def executor(sandboxd: tuple[Sandboxd, SandboxdClient]) -> Iterator[SandboxExecutor]:
    with SandboxExecutor(sandboxd[1], IMAGE, LIMITS) as running:
        yield running


def sh(script: str) -> Command:
    return Command(("sh", "-c", script))


def run(
    executor: SandboxExecutor,
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


def test_streams_lines_with_channels(executor: SandboxExecutor) -> None:
    result, lines = run(executor, "stream", sh("echo one; echo oops >&2; printf tail"))
    assert result.ok
    assert sorted(lines) == [("err", "oops"), ("out", "one"), ("out", "tail")]


def test_inputs_and_outputs(executor: SandboxExecutor) -> None:
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


def test_limits_and_cancellation(executor: SandboxExecutor) -> None:
    timed_out, _ = run(executor, "timeout", sh("sleep 60"), timeout_s=1)
    assert timed_out.timed_out
    assert timed_out.commands[0].duration_s < 10
    limited, lines = run(executor, "output", Command(("yes",)), output_limit=10_000)
    assert limited.output_limited
    assert sum(len(text) + 1 for _, text in lines) <= 10_000
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    cancelled, _ = run(executor, "cancel", sh("sleep 60"), cancel=cancel)
    assert cancelled.cancelled


def test_nothing_of_a_stage_is_left(executor: SandboxExecutor) -> None:
    run(executor, "leave", sh("sleep 300 > /dev/null 2>&1 & sleep 300 > /dev/null 2>&1 &"))
    result, lines = run(executor, "check", sh(PROCESSES))
    assert result.ok
    processes = [text for _, text in lines]
    # PID 1 is apx-init: it took the killed processes and reaped them, no zombie is left.
    assert any(text.endswith("apx-init ") for text in processes), processes
    assert not [text for text in processes if "sleep 300" in text or text.startswith("Z ")]


def test_a_sandbox_is_destroyed_with_its_executor(
    sandboxd: tuple[Sandboxd, SandboxdClient],
) -> None:
    daemon, client = sandboxd
    before = set(daemon.sandboxes)
    with SandboxExecutor(client, IMAGE, LIMITS) as executor:
        [created] = set(daemon.sandboxes) - before
        container = daemon.sandboxes[created].container
        assert run(executor, "x", sh("true"))[0].ok
    assert created not in daemon.sandboxes
    names = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"label={LABEL}", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert container not in names


def test_the_daemon_refuses_what_the_policy_does_not_allow(
    sandboxd: tuple[Sandboxd, SandboxdClient],
) -> None:
    _, client = sandboxd
    with pytest.raises(ExecutorError, match="not allowed"):
        SandboxExecutor(client, "alpine:3", LIMITS).__enter__()
    with pytest.raises(ExecutorError, match="within"):
        SandboxExecutor(client, IMAGE, SandboxLimits(cpus=64, memory_mb=2048, pids=256)).__enter__()
