"""The metrics of the backups (docs/alerts.md): what apparatica-backup-metrics records after a run
of a backup unit, and that the alert rules read only metrics it writes."""

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (
    ROOT / "deploy" / "ansible" / "roles" / "apparatica" / "files" / "apparatica-backup-metrics.py"
)
RULES = ROOT / "deploy" / "prometheus" / "rules" / "backups.yml"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("apparatica_backup_metrics", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


metrics = load_script()


def samples(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return dict(line.rsplit(" ", 1) for line in lines if not line.startswith("#"))


def test_a_success_is_recorded(tmp_path: Path) -> None:
    metrics.record(tmp_path, "backup", True, 1000.4)
    assert samples(tmp_path / "backup.prom") == {
        'apparatica_backup_last_run_success{task="backup"}': "1",
        'apparatica_backup_last_run_timestamp_seconds{task="backup"}': "1000",
        'apparatica_backup_last_success_timestamp_seconds{task="backup"}': "1000",
    }
    assert not list(tmp_path.glob("*.tmp"))
    # The text format of Prometheus: a carriage return breaks the whole file.
    assert b"\r" not in (tmp_path / "backup.prom").read_bytes()


def test_a_failure_keeps_the_last_success(tmp_path: Path) -> None:
    metrics.record(tmp_path, "restore_check", True, 1000)
    metrics.record(tmp_path, "restore_check", False, 2000)
    assert samples(tmp_path / "restore_check.prom") == {
        'apparatica_backup_last_run_success{task="restore_check"}': "0",
        'apparatica_backup_last_run_timestamp_seconds{task="restore_check"}': "2000",
        'apparatica_backup_last_success_timestamp_seconds{task="restore_check"}': "1000",
    }


def test_a_task_that_never_succeeded_has_no_success(tmp_path: Path) -> None:
    metrics.record(tmp_path, "backup", False, 2000)
    metrics.record(tmp_path, "backup", False, 3000)
    assert samples(tmp_path / "backup.prom") == {
        'apparatica_backup_last_run_success{task="backup"}': "0",
        'apparatica_backup_last_run_timestamp_seconds{task="backup"}': "3000",
    }


def test_tasks_have_files_of_their_own(tmp_path: Path) -> None:
    metrics.record(tmp_path, "backup", True, 1000)
    metrics.record(tmp_path, "restore_check", False, 2000)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["backup.prom", "restore_check.prom"]


@pytest.mark.parametrize(
    ("result", "succeeded"), [("success", "1"), ("exit-code", "0"), ("timeout", "0"), (None, "0")]
)
def test_the_result_comes_from_systemd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, result: str | None, succeeded: str
) -> None:
    if result is None:
        monkeypatch.delenv("SERVICE_RESULT", raising=False)
    else:
        monkeypatch.setenv("SERVICE_RESULT", result)
    monkeypatch.setattr(sys, "argv", ["apparatica-backup-metrics", str(tmp_path), "backup"])
    assert metrics.main() == 0
    assert (
        samples(tmp_path / "backup.prom")['apparatica_backup_last_run_success{task="backup"}']
        == succeeded
    )


def test_an_unknown_task_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["apparatica-backup-metrics", str(tmp_path), "vacuum"])
    assert metrics.main() == 2
    assert not list(tmp_path.iterdir())


def test_the_rules_read_the_recorded_metrics() -> None:
    rules = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    expressions = " ".join(rule["expr"] for group in rules["groups"] for rule in group["rules"])
    read = set(re.findall(r"apparatica_backup_\w+", expressions))
    assert read <= set(metrics.HELP)
    for task in re.findall(r'task="(\w+)"', expressions):
        assert task in metrics.TASKS
