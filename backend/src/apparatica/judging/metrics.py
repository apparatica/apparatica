"""Prometheus metrics of the ingestor (NFR-OBS-02), served on `APX_METRICS_PORT`.

The queues are read at every scrape: the checks waiting in each queue (`queue:<queue>`, the
positions the API keeps), how long the oldest of them waits, and the records of `judge:results`
the ingestors have not stored yet. Every ingestor reports the same values: a dashboard takes the
maximum.
"""

import time
from collections.abc import Iterable, Iterator, Sequence
from typing import get_args

import redis
import structlog
from prometheus_client import Counter
from prometheus_client.core import GaugeMetricFamily, Metric
from prometheus_client.registry import Collector

from apparatica.submissions.schemas import SubmissionStatus
from judge.core.jobs import RESULTS_STREAM, position_key

log = structlog.get_logger(__name__)

CHECKS_FINISHED = Counter(
    "apparatica_checks_finished", "Checks given their final status by the ingestor", ["status"]
)
# Every final status from the start, at zero: rate() cannot see the first increment of a series that
# did not exist, and the alert on internal errors would miss the first of them (docs/alerts.md).
for status in get_args(SubmissionStatus):
    if status not in ("queued", "running"):
        CHECKS_FINISHED.labels(status)
RECORDS = Counter(
    "apparatica_ingest_records",
    "Records of judge:results by type and outcome: stored, dropped (refused) or failed",
    ["type", "outcome"],
)


class QueueCollector(Collector):
    def __init__(self, valkey: redis.Redis, queues: Sequence[str]) -> None:
        self._valkey, self._queues = valkey, queues

    def describe(self) -> Iterable[Metric]:
        return self._families()  # without reading Valkey on registration

    def collect(self) -> Iterator[Metric]:
        waiting, oldest, pending = self._families()
        now = time.time()
        try:
            with self._valkey.pipeline(transaction=False) as pipe:
                for queue in self._queues:
                    pipe.zcard(position_key(queue))
                    pipe.zrange(position_key(queue), 0, 0, withscores=True)
                pipe.xlen(RESULTS_STREAM)
                replies = pipe.execute()
        except redis.RedisError as error:  # the scrape still gets the other metrics
            log.warning("queue metrics unavailable", error=str(error))
            return
        for index, queue in enumerate(self._queues):
            count, first = replies[2 * index], replies[2 * index + 1]
            waiting.add_metric([queue], count)
            oldest.add_metric([queue], max(0.0, now - first[0][1]) if first else 0.0)
        pending.add_metric([], replies[-1])
        yield from (waiting, oldest, pending)

    @staticmethod
    def _families() -> tuple[GaugeMetricFamily, GaugeMetricFamily, GaugeMetricFamily]:
        return (
            GaugeMetricFamily(
                "apparatica_queue_waiting", "Checks waiting in the queue", labels=["queue"]
            ),
            GaugeMetricFamily(
                "apparatica_queue_oldest_wait_seconds",
                "How long the oldest check of the queue waits; 0 when none waits",
                labels=["queue"],
            ),
            GaugeMetricFamily(
                "apparatica_results_pending", "Records of judge:results not stored yet"
            ),
        )
