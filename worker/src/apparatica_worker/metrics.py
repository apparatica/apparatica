"""Prometheus metrics of the worker (NFR-OBS-02), served on `APX_METRICS_PORT`.

Slots by pool (`main` for the resource class queues, `rejudge`), the wait of a job in its queue,
and the stages of the attempts the worker reports: their run time by stage type and their status,
where `error` is an internal error of the stage.
"""

from prometheus_client import Counter, Gauge, Histogram

from judge.core.jobs import REJUDGE_QUEUE
from judge.core.stage import StageResult

SLOTS = Gauge("apparatica_worker_slots", "Jobs the pool runs at once", ["pool"])
BUSY_SLOTS = Gauge("apparatica_worker_busy_slots", "Slots running a job", ["pool"])
QUEUE_WAIT = Histogram(
    "apparatica_worker_queue_wait_seconds",
    "From a job queued by the API to a slot taking it; a job requeued after a worker died counts"
    " from its first queuing",
    ["queue"],
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600),
)
STAGES = Counter(
    "apparatica_worker_stages",
    "Stages of reported attempts by type and status",
    ["stage", "status"],
)
STAGE_DURATION = Histogram(
    "apparatica_worker_stage_duration_seconds",
    "Run time of the stages that ran, by type and status",
    ["stage", "status"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300),
)
ATTEMPTS = Counter(
    "apparatica_worker_attempts",
    "Reported attempts by outcome: done, cancelled, or the error code of a pipeline that did not"
    " run",
    ["outcome"],
)


def pool(queue: str) -> str:
    return "rejudge" if queue == REJUDGE_QUEUE else "main"


def observe_attempt(
    results: tuple[StageResult, ...], error_code: str | None, cancelled: bool
) -> None:
    ATTEMPTS.labels(error_code or ("cancelled" if cancelled else "done")).inc()
    for result in results:
        STAGES.labels(result.type, result.status).inc()
        if result.duration_ms is not None:
            STAGE_DURATION.labels(result.type, result.status).observe(result.duration_ms / 1000)
