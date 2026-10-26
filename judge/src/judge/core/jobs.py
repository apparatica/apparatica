"""The check the API hands to a worker through the queue (ADR-0002, specs/07 §3).

The API and the worker share only this module: the API enqueues a Dramatiq message for the
`judge_submission` actor without importing the worker. A worker has no access to the database, so
the job carries everything a check needs.
"""

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from judge.core.package import Slug
from judge.core.stage import SubmissionKind

ACTOR = "judge_submission"
REJUDGE_QUEUE = "judge.rejudge"
RESOURCE_CLASS_QUEUES = {"light": "judge.light", "heavy": "judge.heavy"}
QUEUES = (*RESOURCE_CLASS_QUEUES.values(), REJUDGE_QUEUE)


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
