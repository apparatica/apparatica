"""The orchestrator: one attempt of a check on this worker (specs/07 §3, §5).

Lease and attempt count first: a duplicate message is dropped, and a check that already used its
attempts ends with internal_error without running. Then the package from the cache, a sandbox of
apx-sandboxd, the pipeline of the judge with its events in `sub:<id>` and its stage results in
`judge:results`, the artifacts to the storage and the report.

A waveform job (FR-WAV-05) records the FST of a finished check again: the same lease and attempts,
keyed by the waveform, the pipeline up to the traced stage with the seed of the check and without
events, and one `waveform` record with the FST if the window reproduced the first mismatch.
"""

import contextlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import redis
import structlog
import zstandard

from apparatica_worker.cancel import Cancellation, CancelListener
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
    AttemptStartedRecord,
    JudgeJob,
    StoredArtifact,
    WaveformJob,
    WaveformRecord,
    attempts_key,
    position_key,
)
from judge.core.limits import ResourceClasses, SandboxLimits, sandbox_limits
from judge.core.package import ManifestError, Problem, load_manifest
from judge.core.pipeline import Job, PipelineConfigError, run_pipeline
from judge.core.registry import LanguageModule, UnknownLanguageError, get_language
from judge.core.stage import StageResult

log = structlog.get_logger(__name__)

ATTEMPTS_TTL_S = 7 * 86400  # longer than any check waits and runs
# Files the stages keep for the user, by name (StageOutcome.artifacts), and their artifact kind.
# tb_result holds the expected values of hidden tests: stored, never offered (specs/07 §4.4).
ARTIFACT_KINDS: dict[str, ArtifactKind] = {"trace.fst": "fst", "tb_result.jsonl": "tb_result"}
# Why a waveform job recorded no FST.
TRACE_NOT_REPRODUCED = "TRACE_NOT_REPRODUCED"  # no window, or not around the same mismatch
STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"

ExecutorFactory = Callable[[JudgeJob, SandboxLimits], Executor]


class _UnavailableError(Exception):
    """The pipeline did not run, or its result cannot be kept."""

    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


@dataclass(frozen=True)
class _Package:
    path: Path
    problem: Problem
    language: LanguageModule
    limits: SandboxLimits


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
    cancels: CancelListener | None = None  # the cancel channel of the process

    def __call__(self, job: JudgeJob, queue: str) -> None:
        submission = str(job.submission_id)
        # Taken: no longer waiting. A message requeued after a worker died is not counted again.
        self.valkey.zrem(position_key(queue), submission)
        cancellation = Cancellation()
        lease = Lease(self.valkey, job.submission_id, self.owner, on_lost=cancellation.lose_lease)
        with lease, self._watch(job, cancellation):
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
            self.results.write(
                AttemptStartedRecord(
                    submission_id=job.submission_id, attempt=attempt, token=job.token
                )
            )
            report = self._attempt(job, attempt, cancellation)
            if cancellation.lease_lost:  # another worker runs the check now and reports it
                log.warning("attempt not reported: the lease was lost", submission_id=submission)
                return
            self.reporter.report(report)

    def record_waveform(self, job: WaveformJob, queue: str) -> None:
        """A waveform job (FR-WAV-05); its record goes to the ingestor whatever the outcome."""
        check, waveform = job.check, str(job.waveform_id)
        cancellation = Cancellation()
        lease = Lease(self.valkey, job.waveform_id, self.owner, on_lost=cancellation.lose_lease)
        with lease:
            if not lease.held:
                log.info("duplicate message dropped: waveform in progress", waveform_id=waveform)
                return
            key = attempts_key(job.waveform_id)
            attempt = int(self.valkey.incr(key))
            self.valkey.expire(key, ATTEMPTS_TTL_S)
            log.info("waveform started", waveform_id=waveform, attempt=attempt, queue=queue)
            artifact: StoredArtifact | None = None
            error_code: str | None = ATTEMPTS_EXHAUSTED
            if attempt <= ATTEMPT_MAX:
                try:
                    artifact, error_code = self._waveform(job, cancellation), None
                except _UnavailableError as error:
                    error_code = error.error_code
            if cancellation.lease_lost:  # another worker records it now
                log.warning("waveform not reported: the lease was lost", waveform_id=waveform)
                return
            log.info(
                "waveform finished",
                waveform_id=waveform,
                submission_id=str(check.submission_id),
                error_code=error_code,
                artifact=artifact.key if artifact else None,
            )
            record = WaveformRecord(
                submission_id=check.submission_id,
                token=check.token,
                waveform_id=job.waveform_id,
                artifact=artifact,
                error_code=error_code,
            )
            self.results.write(record, final=True)

    @contextlib.contextmanager
    def _watch(self, job: JudgeJob, cancellation: Cancellation) -> Iterator[None]:
        if self.cancels is None:
            yield
            return
        with self.cancels.watch(job.submission_id, cancellation):
            yield

    def _attempt(self, job: JudgeJob, attempt: int, cancellation: Cancellation) -> AttemptReport:
        if cancellation.cancelled:  # cancelled while it waited: nothing runs
            log.info("cancelled check not run", submission_id=str(job.submission_id))
            return AttemptReport(job, attempt, cancelled=True)
        console = RecordingSink()
        files: dict[tuple[str, str], bytes] = {}
        try:
            package = self._package(job)
            with ValkeyStreamSink(self.valkey, job, attempt) as stream:
                results = self._run(
                    job,
                    package,
                    Job(package.problem, package.path, job.kind, job.seed, job.code.encode()),
                    FanoutSink(console, stream, ResultsSink(self.results, job, attempt)),
                    cancellation,
                    files,
                )
        except _UnavailableError as error:
            return AttemptReport(job, attempt, error_code=error.error_code)
        artifacts = self._store(job, attempt, results, console, stream.journal, files)
        return AttemptReport(
            job, attempt, tuple(results), artifacts, cancelled=cancellation.cancelled
        )

    def _waveform(self, job: WaveformJob, cancellation: Cancellation) -> StoredArtifact:
        """The FST of the traced stage, stored next to the attempts of the check."""
        check = job.check
        package = self._package(check)
        files: dict[tuple[str, str], bytes] = {}
        pipeline = Job(
            package.problem,
            package.path,
            check.kind,
            check.seed,
            check.code.encode(),
            stages=job.stages,
        )
        # Nobody watches the events: the check has finished, its console is stored.
        results = self._run(check, package, pipeline, FanoutSink(), cancellation, files)
        traced = next((result for result in results if result.key == job.stage), None)
        trace = next(
            (data for (stage, name), data in files.items()
             if stage == job.stage and ARTIFACT_KINDS.get(name) == "fst"),
            None,
        )  # fmt: skip
        reproduced = (
            traced is not None
            and traced.metrics.get("first_failure") == job.first_failure.model_dump()
        )
        if trace is None or not reproduced:
            raise _UnavailableError(TRACE_NOT_REPRODUCED)
        try:
            return self.artifacts.put(
                check, f"w-{job.waveform_id}", "fst", job.stage, f"{job.stage}/trace.fst", trace
            )
        except STORAGE_ERRORS as error:
            log.error("waveform not stored", waveform_id=str(job.waveform_id), error=str(error))
            raise _UnavailableError(STORAGE_UNAVAILABLE) from error

    def _package(self, job: JudgeJob) -> _Package:
        try:
            path = self.packages.get(job)
            problem = load_manifest(path)
            language = get_language(problem.language)
            limits = sandbox_limits(problem, self.classes)
        except (PackageError, ManifestError, UnknownLanguageError, ValueError) as error:
            log.error("package unavailable", submission_id=str(job.submission_id), error=str(error))
            raise _UnavailableError(PACKAGE_UNAVAILABLE) from error
        return _Package(path, problem, language, limits)

    def _run(
        self,
        job: JudgeJob,
        package: _Package,
        pipeline: Job,
        sink: FanoutSink,
        cancellation: Cancellation,
        files: dict[tuple[str, str], bytes],
    ) -> list[StageResult]:
        """The pipeline in a sandbox of its own; `files` gets what the stages keep."""
        executor = self.executor(job, package.limits)
        try:
            executor.__enter__()
        except ExecutorError as error:
            log.error("sandbox unavailable", submission_id=str(job.submission_id), error=str(error))
            raise _UnavailableError(SANDBOX_UNAVAILABLE) from error
        try:
            return run_pipeline(
                pipeline,
                package.language,
                executor,
                sink,
                self.classes,
                cancellation.event,
                on_artifact=lambda stage, name, data: files.__setitem__((stage, name), data),
                cancel_note=cancellation.note,
            )
        except PipelineConfigError as error:  # the package passed validation: a platform failure
            log.error(
                "pipeline not runnable", submission_id=str(job.submission_id), error=str(error)
            )
            raise _UnavailableError(PACKAGE_UNAVAILABLE) from error
        finally:
            try:
                executor.__exit__(None, None, None)
            except ExecutorError as error:  # apx-sandboxd removes it when its lifetime ends
                log.warning("sandbox not destroyed", error=str(error))

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
