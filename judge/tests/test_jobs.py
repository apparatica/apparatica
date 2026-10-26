import uuid

import pytest
from pydantic import ValidationError

from judge.core.jobs import (
    QUEUES,
    RESULTS_STREAM,
    JudgeJob,
    attempts_key,
    lease_key,
    position_key,
    queue_name,
    submission_stream_key,
)

JOB = {
    "submission_id": str(uuid.uuid4()),
    "token": "v1.token",
    "problem": "sync-fifo",
    "version": 2,
    "package_uri": "sync-fifo/2-abc.tar.zst",
    "content_hash": "abc",
    "resource_class": "heavy",
    "kind": "submit",
    "seed": 2**63 - 1,
    "code": "module sync_fifo; endmodule\n",
    "toolchain_profile": "sv-2026.10.2",
    "toolchain_image": "ghcr.io/apparatica/toolchain@sha256:" + "a" * 64,
}


def test_queues_follow_the_resource_class() -> None:
    assert queue_name("light") == "judge.light"
    assert queue_name("heavy") == "judge.heavy"
    assert queue_name("light", rejudge=True) == "judge.rejudge"
    assert QUEUES == ("judge.light", "judge.heavy", "judge.rejudge")
    assert position_key("judge.light") == "queue:judge.light"
    submission = uuid.UUID(str(JOB["submission_id"]))
    assert (lease_key(submission), attempts_key(submission)) == (
        f"lease:{submission}",
        f"attempts:{submission}",
    )
    assert submission_stream_key(submission) == f"sub:{submission}"
    assert RESULTS_STREAM == "judge:results"
    with pytest.raises(KeyError):
        queue_name("huge")


def test_a_job_survives_json() -> None:
    job = JudgeJob.model_validate(JOB)
    assert JudgeJob.model_validate_json(job.model_dump_json()) == job
    assert job.model_dump(mode="json") == JOB


@pytest.mark.parametrize("field", [{"seed": 2**63}, {"version": 0}, {"extra": 1}])
def test_a_job_is_checked(field: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        JudgeJob.model_validate(JOB | field)
