"""`finalized` to the submission stream (specs/07 §4.1): the last event a client gets."""

import uuid

import redis.asyncio

from apparatica.submissions.events import FinalizedEvent
from judge.core.jobs import (
    SUBMISSION_STREAM_FIELD,
    SUBMISSION_STREAM_FINAL_TTL_S,
    SUBMISSION_STREAM_MAXLEN,
    submission_stream_key,
)


async def publish_finalized(
    valkey: redis.asyncio.Redis, submission_id: uuid.UUID, event: FinalizedEvent
) -> None:
    """The stream lives 10 minutes more; then the SSE endpoint reads the journal (T1.5)."""
    key = submission_stream_key(submission_id)
    async with valkey.pipeline(transaction=False) as pipe:
        pipe.xadd(
            key,
            {SUBMISSION_STREAM_FIELD: event.model_dump_json()},
            maxlen=SUBMISSION_STREAM_MAXLEN,
            approximate=True,
        )
        pipe.expire(key, SUBMISSION_STREAM_FINAL_TTL_S)
        await pipe.execute()
