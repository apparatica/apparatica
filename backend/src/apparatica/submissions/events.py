"""Events of the submission stream (specs/07 §4.1): the `data:` of `GET /submissions/{id}/events`.

The worker emits the pipeline events of the judge (`judge.core.events`) with the attempt number;
the API adds the queue position and the ingestor the final status. The stream entry id is the SSE
`id:`, the event type is the SSE `event:`.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

from judge.core import events as pipeline
from judge.core.verdict import SubmissionStatus as FinalStatus
from judge.core.verdict import VerdictDetail


class _StreamEvent(BaseModel):
    # Every field is always sent: `type` must be required for the client to narrow the union.
    model_config = ConfigDict(
        extra="forbid", frozen=True, json_schema_serialization_defaults_required=True
    )


Attempt = Annotated[
    int, Field(ge=1, description="Attempt of the check; a new attempt resets the results")
]


class QueueEvent(_StreamEvent):
    """Position in the queue, from the API while the submission waits."""

    type: Literal["queue"] = "queue"
    position: int = Field(ge=1)
    eta_s: int | None = Field(default=None, description="Estimated wait in seconds")


class StageStartEvent(pipeline.StageStartEvent, _StreamEvent):
    attempt: Attempt


class LogEvent(pipeline.LogEvent, _StreamEvent):
    """Console text: whole lines, each with its newline, glued for ~75 ms or up to 8 KB."""

    attempt: Attempt


class HeartbeatEvent(pipeline.HeartbeatEvent, _StreamEvent):
    """Once a second on a silent step."""

    attempt: Attempt


class TestEvent(pipeline.TestEvent, _StreamEvent):
    """A test started or finished: the client replaces the test with this id."""

    attempt: Attempt


class TruncatedEvent(pipeline.TruncatedEvent, _StreamEvent):
    """The stage output hit the limit: the stage was stopped."""

    attempt: Attempt


class StageEndEvent(pipeline.StageEndEvent, _StreamEvent):
    """A finished stage: its partial results are final."""

    attempt: Attempt


class DoneEvent(pipeline.DoneEvent, _StreamEvent):
    """The pipeline of the attempt is over; the status comes with `finalized`."""

    attempt: Attempt


class FinalizedEvent(_StreamEvent):
    """The final status, from the ingestor after it is stored: the last event of the stream."""

    type: Literal["finalized"] = "finalized"
    status: FinalStatus
    verdict_detail: VerdictDetail


class SubmissionEvent(
    RootModel[
        Annotated[
            QueueEvent
            | StageStartEvent
            | LogEvent
            | HeartbeatEvent
            | TestEvent
            | TruncatedEvent
            | StageEndEvent
            | DoneEvent
            | FinalizedEvent,
            Field(discriminator="type"),
        ]
    ]
):
    """An event of the submission stream; the final status comes only with `finalized`."""
