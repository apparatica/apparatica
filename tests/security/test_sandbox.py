"""Code that took over a tool in the sandbox (specs/07 §5, docs/security.md): what it can reach.

The prohibitions of precheck keep such code out of Verilator's C++, so these tests run commands in a
sandbox of apx-sandboxd directly, the way stages run, and check one barrier each.
"""

import re
import subprocess
from collections.abc import Iterator

import pytest

from apparatica_worker.sandboxd.client import SandboxdClient, SandboxExecutor
from apparatica_worker.sandboxd.server import Sandboxd
from harness import IMAGE, LIMITS, RUNTIME, sh, stage, text
from judge.core.stage import Command

SANDBOX_UID = 10001
SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASS|AWS|S3|VALKEY|REDIS|DATABASE|APX_")
# Shell builtins only: counting must not add processes of its own.
PROCESS_COUNT = "set -- /proc/[0-9]*; echo $#"


@pytest.fixture
def executor(client: SandboxdClient) -> Iterator[SandboxExecutor]:
    with SandboxExecutor(client, IMAGE, LIMITS) as running:
        yield running


def test_the_sandbox_runs_under_the_configured_runtime(
    sandboxd: tuple[Sandboxd, tuple[str, int]], executor: SandboxExecutor
) -> None:
    """CI sets runsc: the suite proves itself under gVisor, not under the Docker default."""
    [sandbox] = sandboxd[0].sandboxes.values()
    inspected = subprocess.run(
        ["docker", "inspect", "--format", "{{.HostConfig.Runtime}}", sandbox.container],
        capture_output=True,
        text=True,
        check=True,
    )
    assert inspected.stdout.strip() == RUNTIME


def test_no_privileges_and_no_secrets(executor: SandboxExecutor) -> None:
    script = """
import ctypes, os
status = dict(line.split(":", 1) for line in open("/proc/self/status"))
print(os.getuid(), os.getgid())
print(*(int(status[key], 16) for key in ("CapPrm", "CapEff", "CapBnd")))
print(ctypes.CDLL(None).prctl(39, 0, 0, 0, 0))  # PR_GET_NO_NEW_PRIVS
print(*(os.path.exists(path) for path in ("/var/run/docker.sock", "/run/docker.sock")))
print(*sorted(os.environ))
"""
    result, lines = stage(executor, "privileges", Command(("python3", "-I", "-c", script)))
    assert result.ok, text(lines)
    ids, capabilities, no_new_privs, sockets, environment = (line for _, line in lines)
    assert ids == f"{SANDBOX_UID} {SANDBOX_UID}"
    assert capabilities == "0 0 0"  # permitted, effective, bounding
    assert no_new_privs == "1"
    assert sockets == "False False"  # no Docker socket
    names = environment.split()
    assert not [name for name in names if SECRET_NAME.search(name)], names


def test_no_network(executor: SandboxExecutor) -> None:
    script = """
import socket
print(*(name for _, name in socket.if_nameindex()))
for host, port in (("1.1.1.1", 53), ("8.8.8.8", 443), ("172.17.0.1", 2375), ("10.0.0.1", 80)):
    try:
        socket.create_connection((host, port), timeout=2).close()
        print("connected", host)
    except OSError as error:
        print("refused", host, error.errno)
try:
    socket.getaddrinfo("example.com", 443)
    print("resolved")
except OSError:
    print("no dns")
"""
    result, lines = stage(executor, "network", Command(("python3", "-I", "-c", script)))
    assert result.ok, text(lines)
    out = [line for _, line in lines]
    assert out[0] == "lo", out  # the only interface: loopback
    assert not [line for line in out if line.startswith(("connected", "resolved"))], out


def test_the_root_filesystem_is_read_only(executor: SandboxExecutor) -> None:
    targets = ["/", "/etc", "/opt/apx", "/usr/local/bin", "/home", "/var/tmp", "/root"]
    script = (
        "for d in " + " ".join(targets) + '; do touch "$d/pwned" 2>/dev/null && echo "$d"; done'
    )
    script += "; touch /work/ok /tmp/ok && echo writable"
    result, lines = stage(executor, "filesystem", sh(script))
    assert result.ok, text(lines)
    assert [line for _, line in lines] == ["writable"]


def test_disk_is_bounded(executor: SandboxExecutor) -> None:
    result, lines = stage(
        executor,
        "disk",
        sh("head -c 700m /dev/zero > /work/fill; head -c 100m /dev/zero > /tmp/fill"),
    )
    assert [c.exit_code for c in result.commands] == [1], text(lines)
    assert text(lines).count("No space left on device") == 2


def test_memory_is_bounded(executor: SandboxExecutor) -> None:
    """runc: the OOM killer takes the process. gVisor: it takes the whole sandbox, and the stage
    gets the memory limit instead of an executor error."""
    allocate = f"b = bytearray({LIMITS.memory_mb + 512} * 2**20); print('allocated')"
    result, lines = stage(executor, "memory", Command(("python3", "-I", "-c", allocate)))
    assert "allocated" not in text(lines)
    if RUNTIME == "runsc":
        assert result.memory_exceeded
    else:
        assert result.commands[0].exit_code != 0, text(lines)


def test_a_fork_bomb_hits_the_pids_limit(executor: SandboxExecutor) -> None:
    spawn = """
import os, signal
children = []
try:
    while len(children) < 1000:
        pid = os.fork()
        if pid == 0:
            signal.pause()
            os._exit(0)
        children.append(pid)
except OSError as error:
    print("fork failed", error.errno)
print(len(children))
"""
    result, lines = stage(executor, "spawn", Command(("python3", "-I", "-c", spawn)))
    assert result.ok, text(lines)
    assert lines[0][1] == "fork failed 11", text(lines)  # EAGAIN
    assert int(lines[1][1]) < LIMITS.pids
    bomb, _ = stage(executor, "bomb", sh("bomb() { bomb | bomb & }; bomb; sleep 600"), timeout_s=5)
    assert bomb.timed_out or not bomb.ok


def test_a_background_process_dies_with_its_stage(executor: SandboxExecutor) -> None:
    """A process left by one stage must not rewrite the files of the next one (specs/07 §5.2)."""
    forge = "while :; do echo forged > /work/synth/stat.json; sleep 0.01; done"
    leave = (
        f"(setsid sh -c '{forge}' > /dev/null 2>&1 &);"
        f" nohup sh -c '{forge}' > /dev/null 2>&1 &"
        " for i in $(seq 200); do sleep 600 & done"
    )
    left, lines = stage(executor, "sim", sh(leave))
    assert left.ok, text(lines)
    check = (
        "echo mine > stat.json; sleep 1; cat stat.json; "
        + PROCESS_COUNT
        + "; for i in $(seq 200); do sleep 1 & done; wait"
    )
    result, lines = stage(executor, "synth", sh(check))
    assert result.ok, text(lines)
    out = [line for _, line in lines]
    assert out[0] == "mine"
    # apx-init, apx-run and this shell: nothing of the previous stage, and its orphans were reaped,
    # so 200 new processes fit under the pids limit.
    assert int(out[1]) <= 6, out
