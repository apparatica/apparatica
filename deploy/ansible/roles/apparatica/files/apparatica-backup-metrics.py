#!/usr/bin/env python3
"""Record a run of a backup unit for the alerts (docs/alerts.md): the metrics of the task in a file
of the textfile collector of node-exporter.

    apparatica-backup-metrics /var/lib/apparatica/metrics backup|restore_check

Run by systemd after every run of the unit (ExecStopPost), which sets SERVICE_RESULT: `success` or
the reason of a failure. A failed run keeps the time of the last success; a task that never
succeeded has none. Standard library only: it runs on the server.
"""

import os
import re
import sys
import time
from pathlib import Path

TASKS = ("backup", "restore_check")
LAST_SUCCESS = "apparatica_backup_last_success_timestamp_seconds"
HELP = {
    "apparatica_backup_last_run_success": "Whether the last run of the task succeeded (1) or not.",
    "apparatica_backup_last_run_timestamp_seconds": "When the last run of the task ended.",
    LAST_SUCCESS: "When the last successful run of the task ended.",
}


def last_success(path: Path, task: str) -> str | None:
    if not path.exists():
        return None
    pattern = re.compile(rf'^{LAST_SUCCESS}{{task="{task}"}} (\S+)$', re.MULTILINE)
    found = pattern.search(path.read_text(encoding="utf-8"))
    return found.group(1) if found else None


def record(directory: Path, task: str, succeeded: bool, now: float) -> None:
    path = directory / f"{task}.prom"
    stamp = f"{now:.0f}"
    values = {
        "apparatica_backup_last_run_success": "1" if succeeded else "0",
        "apparatica_backup_last_run_timestamp_seconds": stamp,
        LAST_SUCCESS: stamp if succeeded else last_success(path, task),
    }
    text = "".join(
        f'# HELP {name} {HELP[name]}\n# TYPE {name} gauge\n{name}{{task="{task}"}} {value}\n'
        for name, value in values.items()
        if value is not None
    )
    # Written next to the file and renamed: the collector never reads half of it. It reads only
    # *.prom files, so it skips the temporary one.
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.chmod(0o644)
    os.replace(temporary, path)


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[2] not in TASKS:
        print(f"usage: apparatica-backup-metrics DIRECTORY {'|'.join(TASKS)}", file=sys.stderr)
        return 2
    succeeded = os.environ.get("SERVICE_RESULT") == "success"
    record(Path(sys.argv[1]), sys.argv[2], succeeded, time.time())
    return 0


if __name__ == "__main__":
    sys.exit(main())
