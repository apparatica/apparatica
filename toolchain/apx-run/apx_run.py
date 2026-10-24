#!/usr/bin/python3
"""apx-run: run a stage command so that both of its output streams stay line-buffered and
distinguishable on a single TTY (specs/07 §4.3).

Stages run via `docker exec -t`, which merges stderr into stdout. apx-run gives the command a
separate pseudo-terminal for stdout and for stderr (so tools see a TTY and flush per line), then
writes both to its own stdout: stdout lines as is, stderr lines prefixed with ERR_MARK. The
orchestrator strips the mark and assigns the `err` channel. The mark is cosmetic: verdicts never
depend on it.

Usage: apx-run [--] COMMAND [ARGS...]
Exit status: the command's status; 128+N if it was killed by signal N; 127 if it cannot start.
"""

import contextlib
import os
import pty
import selectors
import signal
import subprocess
import sys
import termios
from types import FrameType

ERR_MARK = b"\x1e"  # ASCII record separator at the start of every stderr line
IDLE_FLUSH_S = 0.05  # partial lines are flushed after this much silence
DRAIN_S = 0.2  # after the command exits, wait this long for output of leftover processes
READ_SIZE = 65536

STDOUT, STDERR = 0, 1


class Output:
    """Writes complete lines of both channels to fd 1, never gluing lines of different channels."""

    def __init__(self) -> None:
        self.pending = [b"", b""]
        self.mid_line: int | None = None  # channel whose partial line was written last

    def feed(self, channel: int, data: bytes) -> None:
        buffer = self.pending[channel] + data
        complete, newline, rest = buffer.rpartition(b"\n")
        if newline:
            self._write(channel, complete + newline)
        self.pending[channel] = rest

    def flush(self) -> None:
        for channel in (STDOUT, STDERR):
            if self.pending[channel]:
                self._write(channel, self.pending[channel])
                self.pending[channel] = b""

    def _write(self, channel: int, data: bytes) -> None:
        if self.mid_line is not None and self.mid_line != channel:
            _write_all(b"\n")
            self.mid_line = None
        if channel == STDERR:
            lines = data.split(b"\n")
            last = len(lines) - 1
            data = b"\n".join(
                line
                # A continued partial line and the empty tail after "\n" start no new line.
                if (i == 0 and self.mid_line == STDERR) or (i == last and not line)
                else ERR_MARK + line
                for i, line in enumerate(lines)
            )
        _write_all(data)
        self.mid_line = None if data.endswith(b"\n") else channel


def _write_all(data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(1, view)
        view = view[written:]


def _open_pty() -> tuple[int, int]:
    """A pseudo-terminal without output post-processing, so "\\n" is not turned into "\\r\\n"."""
    master, slave = pty.openpty()
    attrs = termios.tcgetattr(slave)
    attrs[1] &= ~termios.OPOST
    termios.tcsetattr(slave, termios.TCSANOW, attrs)
    return master, slave


def _exit_status(returncode: int) -> int:
    return 128 - returncode if returncode < 0 else returncode


def run(argv: list[str]) -> int:
    out_master, out_slave = _open_pty()
    err_master, err_slave = _open_pty()
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=out_slave,
            stderr=err_slave,
            start_new_session=True,
        )
    except OSError as error:
        sys.stderr.write(f"apx-run: cannot start {argv[0]!r}: {error.strerror}\n")
        return 127
    finally:
        os.close(out_slave)
        os.close(err_slave)

    def forward(signum: int, _frame: FrameType | None) -> None:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signum)

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, forward)

    output = Output()
    selector = selectors.DefaultSelector()
    selector.register(out_master, selectors.EVENT_READ, STDOUT)
    selector.register(err_master, selectors.EVENT_READ, STDERR)
    exited_idle = 0.0
    while selector.get_map():
        events = selector.select(IDLE_FLUSH_S)
        if not events:
            output.flush()
            if process.poll() is not None:
                # Leftover background processes may keep the terminals open; do not wait forever.
                exited_idle += IDLE_FLUSH_S
                if exited_idle >= DRAIN_S:
                    break
            continue
        exited_idle = 0.0
        for key, _ in events:
            try:
                data = os.read(key.fd, READ_SIZE)
            except OSError:  # EIO: every slave end is closed
                data = b""
            if data:
                output.feed(key.data, data)
            else:
                selector.unregister(key.fd)
    output.flush()
    os.close(out_master)
    os.close(err_master)
    return _exit_status(process.wait())


def main() -> int:
    argv = sys.argv[1:]
    if argv[:1] == ["--"]:
        argv = argv[1:]
    if not argv:
        sys.stderr.write(__doc__ or "")
        return 2
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
