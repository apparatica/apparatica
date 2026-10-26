"""`apparatica-worker`: takes checks from the queues until SIGINT or SIGTERM.

Two Dramatiq workers share the broker: the main slots serve the resource class queues, extra slots
serve `judge.rejudge`, so that a mass rejudge does not take the slots of live users (specs/07 §3).
"""

import logging
import signal
import sys
import threading
from collections.abc import Sequence

import redis
import structlog
from dramatiq import Broker, Worker

from apparatica_worker.broker import Handler, create_broker, declare_actor
from apparatica_worker.logging import configure_logging
from apparatica_worker.runner import JobRunner
from apparatica_worker.settings import WorkerSettings
from judge.core.jobs import REJUDGE_QUEUE

log = structlog.get_logger(__name__)


class _SecondPoolWarning(logging.Filter):
    """Dramatiq warns when a second worker joins a broker: two pools are intended here."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "_WorkerMiddleware" not in record.getMessage()


def create_workers(broker: Broker, settings: WorkerSettings) -> list[Worker]:
    pools = [(set(settings.queues), settings.slots)]
    if settings.rejudge_slots:
        pools.append(({REJUDGE_QUEUE}, settings.rejudge_slots))
    workers = []
    for queues, slots in pools:
        worker = Worker(broker, queues=queues, worker_threads=slots)
        # A check takes long: a worker holds no more messages than it runs, the rest wait for
        # whichever worker is free (the default prefetch is twice the threads).
        worker.queue_prefetch = slots
        workers.append(worker)
    return workers


def run(settings: WorkerSettings, stop: threading.Event, handler: Handler | None = None) -> None:
    """Serve the queues until `stop` is set; the running checks finish first."""
    broker = create_broker(settings.queue_url)
    declare_actor(broker, handler or JobRunner(redis.Redis.from_url(settings.queue_url)))
    workers = create_workers(broker, settings)
    logging.getLogger(f"dramatiq.broker.{type(broker).__name__}").addFilter(_SecondPoolWarning())
    for worker in workers:
        worker.start()
    log.info("worker started", queues=settings.queues, slots=settings.slots)
    stop.wait()
    log.info("worker stopping")
    for worker in workers:
        worker.stop()
    broker.close()


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        print("apparatica-worker takes no arguments: settings come from APX_*", file=sys.stderr)
        return 2
    settings = WorkerSettings()
    configure_logging(settings.log_level, settings.log_format)
    stop = threading.Event()
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_: stop.set())
    run(settings, stop)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
