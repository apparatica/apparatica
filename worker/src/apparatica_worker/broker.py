"""The Dramatiq broker and the `judge_submission` actor (ADR-0002, specs/07 §3).

One owner of restarts: the actor has no retries (`max_retries=0`) and no `TimeLimit` (it would stop
the thread, not the sandbox). Messages of a dead worker are requeued by the Redis broker alone;
duplicates are dropped by the lease of the orchestrator (T1.2b).
"""

from collections.abc import Callable
from typing import Any

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import CurrentMessage, Retries

from judge.core.jobs import ACTOR, QUEUES, RESOURCE_CLASS_QUEUES, JudgeJob

# A job and the queue it came from.
Handler = Callable[[JudgeJob, str], None]


def create_broker(url: str) -> RedisBroker:
    broker = RedisBroker(url=url, middleware=[CurrentMessage(), Retries(max_retries=0)])
    for queue in QUEUES:  # one actor serves every queue: they are declared explicitly
        broker.declare_queue(queue)
    return broker


def declare_actor(broker: dramatiq.Broker, handler: Handler) -> dramatiq.Actor[Any, None]:
    def judge_submission(submission_id: str, payload: dict[str, Any]) -> None:
        job = JudgeJob.model_validate(payload)
        if str(job.submission_id) != submission_id:
            raise ValueError(f"the payload is of {job.submission_id}, not of {submission_id}")
        message = CurrentMessage.get_current_message()
        assert message is not None
        handler(job, message.queue_name)

    declare = dramatiq.actor(
        broker=broker, actor_name=ACTOR, queue_name=RESOURCE_CLASS_QUEUES["light"], max_retries=0
    )
    return declare(judge_submission)
