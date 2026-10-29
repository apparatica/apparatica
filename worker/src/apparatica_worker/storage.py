"""The object storage of a worker (ADR-0013): problem packages in, artifacts out.

The worker's key reads `packages`, writes `artifacts` and reads and writes `build-cache`, nothing
else.
"""

import contextlib
import hashlib
import shutil
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import structlog
import zstandard
from botocore.exceptions import BotoCoreError, ClientError

from judge.core.jobs import ArtifactKind, JudgeJob, StoredArtifact
from judge.core.pack import PackError, content_hash, unpack

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client
else:
    S3Client = Any

log = structlog.get_logger(__name__)

STORAGE_ERRORS = (BotoCoreError, ClientError)


class PackageError(Exception):
    """The package of a job cannot be had: missing, broken or not the one the job names."""


class PackageCache:
    """Packages unpacked on the worker host as `<root>/<content hash>/<slug>/`: a published version
    never changes, and the package directory is named after its problem (specs/06). The stages read
    their files from here."""

    def __init__(self, s3: S3Client, bucket: str, root: Path) -> None:
        self._s3 = s3
        self._bucket = bucket
        self.root = root
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def get(self, job: JudgeJob) -> Path:
        target = self.root / job.content_hash
        if not target.is_dir():
            with self._lock(job.content_hash):
                if not target.is_dir():  # another slot may have fetched it meanwhile
                    self._fetch(job, target)
        return target / job.problem

    def _lock(self, key: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def _fetch(self, job: JudgeJob, target: Path) -> None:
        try:
            data = self._s3.get_object(Bucket=self._bucket, Key=job.package_uri)["Body"].read()
        except STORAGE_ERRORS as error:
            raise PackageError(f"cannot download {job.package_uri}: {error}") from error
        try:
            files = unpack(data)
        except (PackError, zstandard.ZstdError, OSError) as error:  # tarfile errors are OSError
            raise PackageError(f"{job.package_uri} is not a package archive: {error}") from error
        digest = content_hash(files)
        if digest != job.content_hash:
            raise PackageError(f"{job.package_uri}: content hash {digest}, the job names another")
        self.root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".partial-", dir=self.root))
        try:
            for file in files:
                path = PurePosixPath(file.path)
                if path.is_absolute() or ".." in path.parts or not path.parts:
                    raise PackageError(f"{job.package_uri}: file outside the package: {file.path}")
                destination = staging.joinpath(job.problem, *path.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(file.data)
            # Atomic: a directory named by the hash is always complete. Another worker process
            # sharing the cache may have won the race; its copy is the same.
            with contextlib.suppress(OSError):
                staging.rename(target)
            if not target.is_dir():
                raise PackageError(f"cannot store the package in {target}")
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        log.info("package cached", package=job.package_uri, content_hash=job.content_hash)


def artifact_key(submission_id: uuid.UUID, attempt: int | str, name: str) -> str:
    """`<yyyy>/<mm>/<submission_id>/<attempt>/<name>` (specs/07 §4.4): the month of the submission,
    read from its UUIDv7, so that every attempt of a check lands in one place. A recorded waveform
    takes `w-<waveform id>` for the attempt (FR-WAV-05)."""
    created = (
        datetime.fromtimestamp((submission_id.int >> 80) / 1000, UTC)
        if submission_id.version == 7
        else datetime.now(UTC)  # not an id of the API; the key must still be valid
    )
    return f"{created:%Y/%m}/{submission_id}/{attempt}/{name}"


class BuildCacheStore:
    """The `build-cache` bucket (specs/07 §2.3): what the stages built, e.g. simulation binaries,
    for 24 hours (the lifecycle of the bucket). A failure is a miss: the stage builds again."""

    def __init__(self, s3: S3Client, bucket: str) -> None:
        self._s3 = s3
        self._bucket = bucket

    def scoped(self, job: JudgeJob) -> "ScopedBuildCache":
        """The cache of the toolchain of a job: a build of another image is never reused."""
        return ScopedBuildCache(self, job.toolchain_profile, job.toolchain_image)

    def get(self, key: str) -> bytes | None:
        try:
            data: bytes = self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") not in ("NoSuchKey", "404"):
                log.warning("build cache unavailable", key=key, error=str(error))
            return None
        except BotoCoreError as error:
            log.warning("build cache unavailable", key=key, error=str(error))
            return None
        log.info("build cache hit", key=key)
        return data

    def put(self, key: str, data: bytes) -> None:
        try:
            self._s3.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType="application/octet-stream"
            )
        except STORAGE_ERRORS as error:
            log.warning("build not cached", key=key, error=str(error))


class ScopedBuildCache:
    """A `judge.core.cache.BuildCache` of one toolchain: `<profile>/<sha256 of image and key>`."""

    def __init__(self, store: BuildCacheStore, profile: str, image: str) -> None:
        self._store = store
        self._profile = profile
        self._image = image

    def get(self, key: str) -> bytes | None:
        return self._store.get(self._object(key))

    def put(self, key: str, data: bytes) -> None:
        self._store.put(self._object(key), data)

    def _object(self, key: str) -> str:
        digest = hashlib.sha256(f"{self._image}\n{key}".encode()).hexdigest()
        return f"{self._profile}/{digest}"


class ArtifactStore:
    def __init__(self, s3: S3Client, bucket: str) -> None:
        self._s3 = s3
        self._bucket = bucket

    def put(
        self,
        job: JudgeJob,
        attempt: int | str,
        kind: ArtifactKind,
        stage: str | None,
        name: str,
        data: bytes,
    ) -> StoredArtifact:
        """Raises one of STORAGE_ERRORS."""
        key = artifact_key(job.submission_id, attempt, name)
        self._s3.put_object(
            Bucket=self._bucket, Key=key, Body=data, ContentType="application/octet-stream"
        )
        return StoredArtifact(
            kind=kind,
            stage=stage,
            key=key,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )
