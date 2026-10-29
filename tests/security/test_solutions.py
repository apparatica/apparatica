"""Malicious solutions (specs/09 §4.2): each gets its expected verdict for the expected reason.

A case is a file in solutions/ with its expectation in a comment line:

    // expect: status=<verdict> [stage=<stage key>] [limit=<limit kind>] [code=<diagnostic code>]

`stage` is where the check fails first; nothing runs after it (a forbidden solution never reaches
Verilator). `code` is among the codes of the errors of that stage.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from apparatica_worker.sandboxd.client import SandboxdClient
from harness import HERE, judge

CASES = sorted((HERE / "solutions").glob("*.sv"))
EXPECT = re.compile(r"^// expect: (.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Expectation:
    status: str
    stage: str | None = None
    limit: str | None = None
    code: str | None = None


def expectation(path: Path) -> Expectation:
    found = EXPECT.search(path.read_text(encoding="utf-8"))
    assert found, f"{path.name}: no `// expect:` line"
    fields = dict(item.split("=", 1) for item in found.group(1).split())
    return Expectation(**fields)


def test_every_case_has_an_expectation() -> None:
    assert CASES
    for path in CASES:
        expectation(path)


@pytest.mark.parametrize("path", CASES, ids=[path.stem for path in CASES])
def test_solution(client: SandboxdClient, path: Path) -> None:
    expected = expectation(path)
    check = judge(client, path.read_bytes())
    verdict, why = check.verdict, check.describe()
    assert verdict.status == expected.status, why
    assert verdict.detail.limit == expected.limit, why
    first = verdict.detail.first_failure
    assert (first.stage if first else None) == expected.stage, why
    if first is not None:
        failed = next(r for r in check.results if r.key == first.stage)
        later = [r.status for r in check.results if r.ordinal > failed.ordinal]
        assert set(later) <= {"skipped"}, why
        if expected.code is not None:
            assert expected.code in [d.code for d in failed.summary.diagnostics], why
