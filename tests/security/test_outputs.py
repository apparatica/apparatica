"""Result files of a simulation that took over the testbench (specs/07 §5.2): the stage fails with
OUTPUT_INVALID instead of a verdict, and the judge goes on."""

import pytest

from apparatica_worker.sandboxd.client import SandboxdClient
from harness import PACKAGE, judge
from judge.core.verdict import Verdict, VerdictDetail

REFERENCE = (PACKAGE / "reference" / "counter.sv").read_bytes()


def test_the_reference_is_accepted(client: SandboxdClient) -> None:
    check = judge(client, REFERENCE, kind="submit")
    assert check.verdict.status == "accepted", check.describe()


@pytest.mark.parametrize(
    "stage",
    [
        pytest.param("sim_junk", id="records-breaking-the-protocol"),
        pytest.param("sim_huge", id="file-over-the-size-limit"),
    ],
)
def test_a_forged_result_file_is_not_a_verdict(client: SandboxdClient, stage: str) -> None:
    check = judge(client, REFERENCE, stages=("precheck", stage))
    expected = Verdict(
        status="internal_error", detail=VerdictDetail(error_codes=["OUTPUT_INVALID"])
    )
    assert check.verdict == expected, check.describe()
