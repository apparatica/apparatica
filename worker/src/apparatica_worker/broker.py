"""The Dramatiq broker and the actors `judge_submission` and `judge_waveform` (ADR-0002,
specs/07 §3).

One owner of restarts: the actors have no retries (`max_retries=0`) and no `TimeLimit` (it would
stop the thread, not the sandbox). Messages of a dead worker are requeued by the Redis broker
alone; duplicates are dropped by the lease of the orchestrator (T1.2b).
"""

from collections.abc import Callable
from typing import Any

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import CurrentMessage, Retries

from judge.core.jobs import (
    ACTOR,
    QUEUES,
    RESOURCE_CLASS_QUEUES,
    WAVEFORM_ACTOR,
    JudgeJob,
    WaveformJob,
)

# A job and the queue it came from.
Handler = Callable[[JudgeJob, str], None]
WaveformHandler = Callable[[WaveformJob, str], None]


def create_broker(url: str) -> RedisBroker:
    broker = RedisBroker(url=url, middleware=[CurrentMessage(), Retries(max_retries=0)])
    for queue in QUEUES:  # the actors serve every queue: they are declared explicitly
        broker.declare_queue(queue)
    return broker


def _queue() -> str:
    message = CurrentMessage.get_current_message()
    assert message is not None
    return message.queue_name


def _declare(broker: dramatiq.Broker, name: str) -> Callable[..., dramatiq.Actor[Any, None]]:
    return dramatiq.actor(
        broker=broker, actor_name=name, queue_name=RESOURCE_CLASS_QUEUES["light"], max_retries=0
    )


def declare_actor(broker: dramatiq.Broker, handler: Handler) -> dramatiq.Actor[Any, None]:
    def judge_submission(submission_id: str, payload: dict[str, Any]) -> None:
        job = JudgeJob.model_validate(payload)
        if str(job.submission_id) != submission_id:
            raise ValueError(f"the payload is of {job.submission_id}, not of {submission_id}")
        handler(job, _queue())

    return _declare(broker, ACTOR)(judge_submission)


def declare_waveform_actor(
    broker: dramatiq.Broker, handler: WaveformHandler
) -> dramatiq.Actor[Any, None]:
    def judge_waveform(waveform_id: str, payload: dict[str, Any]) -> None:
        job = WaveformJob.model_validate(payload)
        if str(job.waveform_id) != waveform_id:
            raise ValueError(f"the payload is of {job.waveform_id}, not of {waveform_id}")
        handler(job, _queue())

    return _declare(broker, WAVEFORM_ACTOR)(judge_waveform)
