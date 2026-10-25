from pathlib import Path

import pytest

from changed_problems import packages, select

EXISTING = ["problems/mux4", "problems/sync-fifo"]


@pytest.mark.parametrize(
    ("changed", "selected"),
    [
        (["problems/mux4/tb/tb_top.sv"], ["problems/mux4"]),
        (["problems/mux4/problem.yaml", "problems/mux4/statement.md"], ["problems/mux4"]),
        (["problems/sync-fifo/x.sv", "problems/mux4/x.sv"], EXISTING),
        (["problems/README.md", "problems/LICENSE"], []),
        (["problems/removed/problem.yaml"], []),
        (["docs/judge.md", "web/package.json", "backend/src/x.py"], []),
        (["judge/src/judge/core/pipeline.py"], EXISTING),
        (["judge/poetry.lock"], EXISTING),
        (["toolchain/sv/apx_tb_pkg.sv"], EXISTING),
        (["config/resource-classes.yaml"], EXISTING),
        ([".github/workflows/problems.yml"], EXISTING),
        (["judge/tests/test_cli.py", "judge/README.md"], []),
    ],
)
def test_select(changed: list[str], selected: list[str]) -> None:
    assert select(changed, EXISTING) == selected


def test_packages(tmp_path: Path) -> None:
    for name in ("b-task", "a-task"):
        (tmp_path / "problems" / name).mkdir(parents=True)
        (tmp_path / "problems" / name / "problem.yaml").write_text("", encoding="utf-8")
    (tmp_path / "problems" / "drafts").mkdir()
    assert packages(tmp_path) == ["problems/a-task", "problems/b-task"]
