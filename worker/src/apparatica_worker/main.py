"""`apparatica-worker`: takes checks from the queues until SIGINT or SIGTERM.

Two Dramatiq workers share the broker: the main slots serve the resource class queues, extra slots
serve `judge.rejudge`, so that a mass rejudge does not take the slots of live users (specs/07 §3).
"""

import logging
import signal
import sys
import threading
from collections.abc import Sequence

import boto3
import redis
import structlog
from botocore.config import Config
from dramatiq import Broker, Worker

from apparatica_worker.broker import (
    Handler,
    WaveformHandler,
    create_broker,
    declare_actor,
    declare_waveform_actor,
)
from apparatica_worker.cancel import CancelListener
from apparatica_worker.logging import configure_logging
from apparatica_worker.orchestrator import Orchestrator
from apparatica_worker.report import StreamReporter
from apparatica_worker.sandboxd.client import SandboxdClient, SandboxExecutor
from apparatica_worker.settings import WorkerSettings
from apparatica_worker.storage import ArtifactStore, BuildCacheStore, PackageCache
from apparatica_worker.stream import ResultsStream
from judge.core.jobs import REJUDGE_QUEUE
from judge.core.limits import load_resource_classes

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


class SandboxRuntimeError(RuntimeError):
    """apx-sandboxd runs another runtime than the worker expects (ADR-0003: runsc in production)."""


def create_orchestrator(settings: WorkerSettings) -> Orchestrator:
    sandboxd = SandboxdClient(settings.sandboxd_socket)
    runtime = sandboxd.request({"op": "info"})["runtime"]
    if runtime != settings.sandbox_runtime:
        raise SandboxRuntimeError(
            f"apx-sandboxd runs {runtime}, APX_SANDBOX_RUNTIME is {settings.sandbox_runtime}"
        )
    secret = settings.s3_secret_access_key
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=secret.get_secret_value() if secret else None,
        config=Config(s3={"addressing_style": "path"}, retries={"mode": "standard"}),
    )
    # A hung Valkey must fail a write, not block the pipeline that emits events.
    valkey = redis.Redis.from_url(settings.queue_url, socket_timeout=5, socket_connect_timeout=5)
    results = ResultsStream(valkey)
    return Orchestrator(
        valkey=valkey,
        packages=PackageCache(s3, settings.s3_bucket_packages, settings.package_cache),
        artifacts=ArtifactStore(s3, settings.s3_bucket_artifacts),
        executor=lambda job, limits: SandboxExecutor(sandboxd, job.toolchain_image, limits),
        classes=load_resource_classes(settings.resource_classes),
        results=results,
        reporter=StreamReporter(results),
        owner=settings.worker_id,
        cancels=CancelListener(valkey),
        build_cache=BuildCacheStore(s3, settings.s3_bucket_build_cache),
    )


def run(
    settings: WorkerSettings,
    stop: threading.Event,
    handler: Handler | None = None,
    waveforms: WaveformHandler | None = None,
) -> None:
    """Serve the queues until `stop` is set; the running checks finish first. Checks go to
    `handler` and waveform jobs to `waveforms`, both the orchestrator by default."""
    broker = create_broker(settings.queue_url)
    if handler is None:
        orchestrator = create_orchestrator(settings)
        handler, waveforms = orchestrator, waveforms or orchestrator.record_waveform
    cancels = handler.cancels if isinstance(handler, Orchestrator) else None
    if cancels is not None:
        cancels.start()  # before the first check: a cancel must find it listening
    declare_actor(broker, handler)
    if waveforms is not None:
        declare_waveform_actor(broker, waveforms)
    workers = create_workers(broker, settings)
    logging.getLogger(f"dramatiq.broker.{type(broker).__name__}").addFilter(_SecondPoolWarning())
    for worker in workers:
        worker.start()
    log.info("worker started", queues=settings.queues, slots=settings.slots)
    stop.wait()
    log.info("worker stopping")
    for worker in workers:
        worker.stop()
    if cancels is not None:
        cancels.stop()
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
