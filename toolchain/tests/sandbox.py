"""A container of the toolchain image started like the orchestrator starts it (specs/07 §5.1)."""

import os
import shlex
import subprocess
import uuid
from collections.abc import Mapping
from dataclasses import dataclass

IMAGE = os.environ.get("TOOLCHAIN_IMAGE", "apparatica-toolchain:dev")
SANDBOX_UID = 10001

# specs/07 §5.1 with the runc runtime; the orchestrator adds runsc on staging and production.
SANDBOX_FLAGS = [
    "--network=none",
    "--read-only",
    f"--tmpfs=/work:exec,size=512m,uid={SANDBOX_UID},gid={SANDBOX_UID}",
    "--tmpfs=/tmp:size=64m",
    "--cap-drop=ALL",
    "--security-opt=no-new-privileges",
    "--pids-limit=256",
    "--memory=2g",
    "--memory-swap=2g",
    "--cpus=2",
]

Result = subprocess.CompletedProcess[bytes]


def output(result: Result) -> str:
    """Both streams of a command, for assertion messages."""
    return (result.stdout + result.stderr).decode(errors="replace")


@dataclass(frozen=True)
class Sandbox:
    container: str

    @classmethod
    def start(cls) -> "Sandbox":
        name = f"apx-toolchain-test-{uuid.uuid4().hex[:8]}"
        argv = ["docker", "run", "-d", "--rm", "--name", name, *SANDBOX_FLAGS, IMAGE]
        started = subprocess.run(
            [*argv, "sleep", "infinity"], capture_output=True, text=True, check=False
        )
        if started.returncode != 0:
            raise RuntimeError(f"cannot start {IMAGE}: {started.stderr.strip()}")
        return cls(name)

    def remove(self) -> None:
        subprocess.run(["docker", "rm", "-f", self.container], capture_output=True, check=False)

    def exec(
        self,
        argv: list[str],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        tty: bool = False,
        stdin: bytes | None = None,
        timeout: float = 300,
    ) -> Result:
        """Run a command in the container with `docker exec`, like a pipeline stage."""
        options = ["-t"] if tty else []
        if stdin is not None:
            options.append("-i")
        if cwd is not None:
            options += ["-w", cwd]
        for key, value in (env or {}).items():
            options += ["-e", f"{key}={value}"]
        return subprocess.run(
            ["docker", "exec", *options, self.container, *argv],
            input=stdin,
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    def write(self, path: str, text: str) -> None:
        result = self.exec(["sh", "-c", f"cat > {shlex.quote(path)}"], stdin=text.encode())
        assert result.returncode == 0, output(result)

    def read(self, path: str) -> str:
        result = self.exec(["cat", path])
        assert result.returncode == 0, output(result)
        return result.stdout.decode()

    def mkdtemp(self) -> str:
        result = self.exec(["mktemp", "-d", "-p", "/work"])
        assert result.returncode == 0, output(result)
        return result.stdout.decode().strip()
