#!/usr/bin/python3
"""apx-init: PID 1 of the sandbox container (ADR-0003, S6). Reaps every orphan, never exits on its
own.

Between stages the orchestrator runs `kill -KILL -1` as the sandbox user: the kernel spares PID 1,
so the container lives on, and the processes of the stage become zombies that only PID 1 can reap.
`sleep infinity` would leave them taking `--pids-limit`; `docker run --init` exits together with
its only child. SIGTERM and SIGINT (`docker stop`) end apx-init and with it the container.

Signals are blocked and taken with sigtimedwait: a child that exits between reaping and waiting
still wakes the loop.
"""

import os
import signal
import sys

STOP = {signal.SIGTERM, signal.SIGINT}
WAKE = {signal.SIGCHLD, *STOP}
POLL_S = 1.0  # a safety net: reap at least this often


def reap() -> None:
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def main() -> int:
    signal.pthread_sigmask(signal.SIG_BLOCK, WAKE)
    while True:
        reap()
        received = signal.sigtimedwait(WAKE, POLL_S)
        if received is not None and received.si_signo in STOP:
            return 0


if __name__ == "__main__":
    sys.exit(main())
