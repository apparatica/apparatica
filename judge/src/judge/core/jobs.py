"""The check the API hands to a worker through the queue and what the worker returns (ADR-0002,
ADR-0008, ADR-0009, specs/07 §3, §4).

The API, the worker and the ingestor share only this module: the API enqueues a Dramatiq message
for the `judge_submission` actor without importing the worker, the worker writes the events of a
check to its submission stream and the results to `judge:results`. A worker has no access to the
database, so the job carries everything a check needs and the results carry the job token.
"""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from judge.core.package import Slug
from judge.core.stage import StageResult, SubmissionKind

ACTOR = "judge_submission"
REJUDGE_QUEUE = "judge.rejudge"
RESOURCE_CLASS_QUEUES = {"light": "judge.light", "heavy": "judge.heavy"}
QUEUES = (*RESOURCE_CLASS_QUEUES.values(), REJUDGE_QUEUE)


# A check runs at most this many times: once, and again after its worker died (specs/07 §3).
ATTEMPT_MAX = 2
LEASE_TTL_S = 15  # a worker holds the lease of a running check and renews it ...
LEASE_RENEW_S = 5  # ... this often; a dead worker loses it within the TTL


def lease_key(submission_id: uuid.UUID) -> str:
    """Who runs the check now: the worker id, with a TTL (SET NX)."""
    return f"lease:{submission_id}"


def attempts_key(submission_id: uuid.UUID) -> str:
    """How many times a worker started the check (INCR)."""
    return f"attempts:{submission_id}"


# The events of a check (specs/07 §4.1): one stream per submission, each entry holds one JSON event
# in the field `e`; the entry id is the SSE id. The ingestor shortens the TTL after `finalized`.
SUBMISSION_STREAM_FIELD = "e"
SUBMISSION_STREAM_MAXLEN = 5000  # approximate (MAXLEN ~)
SUBMISSION_STREAM_TTL_S = 86400  # a stream whose check was never finalized does not stay forever

# The results of all checks for the ingestor (ADR-0009): each entry holds one JSON record in `r`.
RESULTS_STREAM = "judge:results"
RESULTS_STREAM_FIELD = "r"


def submission_stream_key(submission_id: uuid.UUID) -> str:
    return f"sub:{submission_id}"


def queue_name(resource_class: str, *, rejudge: bool = False) -> str:
    """`judge.<resource class>`; rejudges always go to their own queue."""
    return REJUDGE_QUEUE if rejudge else RESOURCE_CLASS_QUEUES[resource_class]


def position_key(queue: str) -> str:
    """Sorted set of the waiting submissions of a queue, scored by the time they were queued."""
    return f"queue:{queue}"


class JudgeJob(BaseModel):
    """The payload of a `judge_submission` message."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    submission_id: uuid.UUID
    token: str = Field(description="Job token: the ingestor accepts results only with it")
    problem: Slug
    version: Annotated[int, Field(ge=1)]
    package_uri: str = Field(description="Object key of the package in the packages bucket")
    content_hash: str = Field(description="sha256 of the package: the cache key on the worker")
    resource_class: str
    kind: SubmissionKind
    seed: Annotated[int, Field(ge=0, lt=2**63)]
    code: str
    toolchain_profile: str
    toolchain_image: str = Field(description="Image with its digest: <image>@sha256:<digest>")


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    submission_id: uuid.UUID
    attempt: Annotated[int, Field(ge=1)]
    token: str = Field(description="The job token of the check: the ingestor verifies it")


# tb_result holds the expected values of hidden tests: stored, never offered (specs/07 §4.4).
ArtifactKind = Literal["log", "events", "fst", "tb_result"]


class StoredArtifact(BaseModel):
    """A file of an attempt in the `artifacts` bucket (`artifacts`, specs/04 §4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ArtifactKind
    stage: str | None
    key: str
    size_bytes: Annotated[int, Field(ge=0)]
    sha256: str


class StageEndRecord(_Record):
    """A stage finished: partial results are stored as they come."""

    type: Literal["stage_end"] = "stage_end"
    result: StageResult


class DoneRecord(_Record):
    """The pipeline finished: every stage result of the attempt and its artifacts. The ingestor
    aggregates the verdict from it; `stage_end` records before it may have been lost."""

    type: Literal["done"] = "done"
    results: tuple[StageResult, ...]
    artifacts: tuple[StoredArtifact, ...]


class AttemptFailedRecord(_Record):
    """The pipeline did not run (no attempts left, no package, no sandbox): internal_error."""

    type: Literal["attempt_failed"] = "attempt_failed"
    error_code: str


type ResultRecord = Annotated[
    StageEndRecord | DoneRecord | AttemptFailedRecord, Field(discriminator="type")
]
RESULT_RECORD: TypeAdapter[ResultRecord] = TypeAdapter(ResultRecord)
