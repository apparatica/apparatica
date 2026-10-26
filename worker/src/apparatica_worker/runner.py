"""What a worker does with a job it takes. The orchestrator runs it in the sandbox from T1.2b; until
then the job only leaves its queue position."""

import redis
import structlog

from judge.core.jobs import JudgeJob, position_key

log = structlog.get_logger(__name__)


class JobRunner:
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def __call__(self, job: JudgeJob, queue: str) -> None:
        # Taken: no longer waiting. A message requeued after a worker died is not counted again.
        self._client.zrem(position_key(queue), str(job.submission_id))
        log.info("job taken", submission_id=str(job.submission_id), queue=queue)
