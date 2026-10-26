"""The orchestrator: one attempt of a check on this worker (specs/07 §3, §5).

Lease and attempt count first: a duplicate message is dropped, and a check that already used its
attempts ends with internal_error without running. Then the package from the cache, a sandbox of
apx-sandboxd, the pipeline of the judge with its events in `sub:<id>` and its stage results in
`judge:results`, the artifacts to the storage and the report.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass

import redis
import structlog
import zstandard

from apparatica_worker.lease import Lease
from apparatica_worker.report import (
    ATTEMPTS_EXHAUSTED,
    PACKAGE_UNAVAILABLE,
    SANDBOX_UNAVAILABLE,
    AttemptReport,
    RecordingSink,
    Reporter,
)
from apparatica_worker.storage import STORAGE_ERRORS, ArtifactStore, PackageCache, PackageError
from apparatica_worker.stream import ResultsSink, ResultsStream, ValkeyStreamSink
from judge.core.events import FanoutSink
from judge.core.executor import Executor, ExecutorError
from judge.core.jobs import (
    ATTEMPT_MAX,
    ArtifactKind,
    JudgeJob,
    StoredArtifact,
    attempts_key,
    position_key,
)
from judge.core.limits import ResourceClasses, SandboxLimits, sandbox_limits
from judge.core.package import ManifestError, load_manifest
from judge.core.pipeline import Job, PipelineConfigError, run_pipeline
from judge.core.registry import UnknownLanguageError, get_language
from judge.core.stage import StageResult

log = structlog.get_logger(__name__)

ATTEMPTS_TTL_S = 7 * 86400  # longer than any check waits and runs
# Files the stages keep for the user, by name (StageOutcome.artifacts), and their artifact kind.
# tb_result holds the expected values of hidden tests: stored, never offered (specs/07 §4.4).
ARTIFACT_KINDS: dict[str, ArtifactKind] = {"trace.fst": "fst", "tb_result.jsonl": "tb_result"}

ExecutorFactory = Callable[[JudgeJob, SandboxLimits], Executor]


@dataclass
class Orchestrator:
    valkey: redis.Redis
    packages: PackageCache
    artifacts: ArtifactStore
    executor: ExecutorFactory  # SandboxExecutor of apx-sandboxd
    classes: ResourceClasses
    results: ResultsStream  # stage results as the stages end
    reporter: Reporter  # the attempt: StreamReporter of the same stream
    owner: str  # this worker, the value of its leases

    def __call__(self, job: JudgeJob, queue: str) -> None:
        submission = str(job.submission_id)
        # Taken: no longer waiting. A message requeued after a worker died is not counted again.
        self.valkey.zrem(position_key(queue), submission)
        with Lease(self.valkey, job.submission_id, self.owner) as lease:
            if not lease.held:
                log.info("duplicate message dropped: the check runs", submission_id=submission)
                return
            key = attempts_key(job.submission_id)
            attempt = int(self.valkey.incr(key))
            self.valkey.expire(key, ATTEMPTS_TTL_S)
            log.info("attempt started", submission_id=submission, attempt=attempt, queue=queue)
            if attempt > ATTEMPT_MAX:
                self.reporter.report(AttemptReport(job, attempt, error_code=ATTEMPTS_EXHAUSTED))
                return
            self.reporter.report(self._attempt(job, attempt, cancel=lease.lost))

    def _attempt(self, job: JudgeJob, attempt: int, cancel: threading.Event) -> AttemptReport:
        try:
            package = self.packages.get(job)
            problem = load_manifest(package)
            language = get_language(problem.language)
            limits = sandbox_limits(problem, self.classes)
        except (PackageError, ManifestError, UnknownLanguageError, ValueError) as error:
            log.error("package unavailable", submission_id=str(job.submission_id), error=str(error))
            return AttemptReport(job, attempt, error_code=PACKAGE_UNAVAILABLE)

        executor = self.executor(job, limits)
        try:
            executor.__enter__()
        except ExecutorError as error:
            log.error("sandbox unavailable", submission_id=str(job.submission_id), error=str(error))
            return AttemptReport(job, attempt, error_code=SANDBOX_UNAVAILABLE)
        console = RecordingSink()
        files: dict[tuple[str, str], bytes] = {}
        try:
            with ValkeyStreamSink(self.valkey, job, attempt) as stream:
                results = run_pipeline(
                    Job(problem, package, job.kind, job.seed, job.code.encode()),
                    language,
                    executor,
                    FanoutSink(console, stream, ResultsSink(self.results, job, attempt)),
                    self.classes,
                    cancel,
                    on_artifact=lambda stage, name, data: files.__setitem__((stage, name), data),
                )
        except PipelineConfigError as error:  # the package passed validation: a platform failure
            log.error(
                "pipeline not runnable", submission_id=str(job.submission_id), error=str(error)
            )
            return AttemptReport(job, attempt, error_code=PACKAGE_UNAVAILABLE)
        finally:
            try:
                executor.__exit__(None, None, None)
            except ExecutorError as error:  # apx-sandboxd removes it when its lifetime ends
                log.warning("sandbox not destroyed", error=str(error))
        artifacts = self._store(job, attempt, results, console, stream.journal, files)
        return AttemptReport(job, attempt, tuple(results), artifacts)

    def _store(
        self,
        job: JudgeJob,
        attempt: int,
        results: list[StageResult],
        console: RecordingSink,
        events: list[bytes],
        files: dict[tuple[str, str], bytes],
    ) -> tuple[StoredArtifact, ...]:
        """Logs, events and the files of the stages. A file that cannot be stored is a lost
        artifact, not a lost check: the results stand."""
        compress = zstandard.ZstdCompressor(level=10).compress
        uploads: list[tuple[ArtifactKind, str | None, str, bytes]] = [
            ("log", r.key, f"logs/{r.key}.log.zst", compress(console.log_text(r.key)))
            for r in results
            if r.started_at is not None
        ]
        uploads.append(("events", None, "events.jsonl.zst", compress(b"".join(events))))
        for (key, file), data in sorted(files.items()):
            known = ARTIFACT_KINDS.get(file)
            if known is None:
                log.warning("unknown artifact dropped", stage=key, name=file)
                continue
            uploads.append((known, key, f"{key}/{file}", data))
        stored = []
        for kind, stage, name, data in uploads:
            try:
                stored.append(self.artifacts.put(job, attempt, kind, stage, name, data))
            except STORAGE_ERRORS as error:
                log.error("artifact not stored", name=name, error=str(error))
        return tuple(stored)
