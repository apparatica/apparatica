"""Problem import (specs/06 §6, FR-PKG-06): packages of the problem repository into the platform.

A new `(slug, version)` becomes a problem version, its package goes to the `packages` bucket.
The same version with the same content hash changes nothing; with another hash it is refused,
because a published version is immutable. An import is atomic: one refused package leaves the
database as it was. `judge validate` has already run in CI, so the import checks only the
manifest, the hash and what the platform knows: difficulty levels, tags, catalogue numbers.
"""

import asyncio
import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.core.db import Database
from apparatica.core.ids import uuid7
from apparatica.core.storage import Storage
from apparatica.problems.models import Problem, ProblemVersion, ReferenceSolution, Tag
from judge.core.pack import content_hash, pack, package_files
from judge.core.package import Problem as Manifest
from judge.core.package import Slug, load_manifest

TAGS_FILE = "tags.yaml"
PACKAGE_CONTENT_TYPE = "application/zstd"


class TagEntry(BaseModel):
    """One entry of `problems/tags.yaml`; the order of the file is the sort order."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slug: Slug
    title: str = Field(min_length=1, max_length=40)


class ImportRefusedError(Exception):
    def __init__(self, issues: list[str]) -> None:
        super().__init__("; ".join(issues))
        self.issues = issues


def load_tags(path: Path) -> list[TagEntry]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        tags = TypeAdapter(list[TagEntry]).validate_python(data)
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ImportRefusedError([f"{path}: {error}"]) from error
    slugs = [tag.slug for tag in tags]
    duplicates = sorted({slug for slug in slugs if slugs.count(slug) > 1})
    if duplicates:
        raise ImportRefusedError([f"{path}: duplicate tags: {', '.join(duplicates)}"])
    return tags


@dataclass(frozen=True)
class Package:
    manifest: Manifest
    files: dict[str, bytes]
    content_hash: str
    archive: bytes

    @property
    def name(self) -> str:
        return f"{self.manifest.id} v{self.manifest.version}"

    @property
    def key(self) -> str:
        """Object key in the packages bucket: content-addressed, so uploads are idempotent."""
        return f"{self.manifest.id}/{self.manifest.version}-{self.content_hash}.tar.zst"

    def text(self, path: str) -> str:
        try:
            return self.files[path].decode("utf-8")
        except (KeyError, UnicodeDecodeError) as error:
            raise ImportRefusedError(
                [f"{self.name}: {path}: not a UTF-8 file of the package"]
            ) from error


def read_package(path: Path) -> Package:
    """Raises ManifestError or PackError for a broken package."""
    manifest = load_manifest(path)
    files = package_files(path)
    return Package(
        manifest=manifest,
        files={file.path: file.data for file in files},
        content_hash=content_hash(files),
        archive=pack(files),
    )


@dataclass(frozen=True)
class Imported:
    package: Package
    outcome: Literal["created", "unchanged"]
    published: bool


async def import_packages(
    database: Database,
    storage: Storage,
    bucket: str,
    packages: Sequence[Package],
    tags: Sequence[TagEntry],
    difficulties: Collection[str],
    *,
    publish: bool,
) -> list[Imported]:
    """Import all packages or none; raises ImportRefusedError with every issue found."""
    issues = _catalogue_issues(packages, tags, difficulties)
    if issues:
        raise ImportRefusedError(issues)
    results: list[Imported] = []
    async with database.sessions.begin() as session:
        await _sync_tags(session, tags)
        for package in packages:
            try:
                results.append(await _import(session, package, publish=publish))
            except ImportRefusedError as error:
                issues.extend(error.issues)
        if issues:
            raise ImportRefusedError(issues)  # rolls the transaction back
        # Before the commit: a version in the database always has its package in storage.
        for result in results:
            if result.outcome == "created":
                await asyncio.to_thread(
                    storage.put,
                    bucket,
                    result.package.key,
                    result.package.archive,
                    PACKAGE_CONTENT_TYPE,
                )
    return results


def _catalogue_issues(
    packages: Sequence[Package], tags: Sequence[TagEntry], difficulties: Collection[str]
) -> list[str]:
    known_tags = {tag.slug for tag in tags}
    issues = []
    for package in packages:
        manifest = package.manifest
        if manifest.difficulty not in difficulties:
            issues.append(
                f"{package.name}: difficulty {manifest.difficulty!r} is not in"
                f" difficulties.yaml ({', '.join(difficulties)})"
            )
        unknown = [tag for tag in manifest.tags if tag not in known_tags]
        if unknown:
            issues.append(f"{package.name}: tags not in {TAGS_FILE}: {', '.join(unknown)}")
    return issues


async def _sync_tags(session: AsyncSession, tags: Sequence[TagEntry]) -> None:
    """Upsert the tags of the file. Tags missing from it stay: old versions may refer to them."""
    if not tags:
        return
    statement = insert(Tag).values(
        [{"slug": tag.slug, "title": tag.title, "sort": sort} for sort, tag in enumerate(tags)]
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[Tag.slug],
            set_={"title": statement.excluded.title, "sort": statement.excluded.sort},
        )
    )


async def _import(session: AsyncSession, package: Package, *, publish: bool) -> Imported:
    manifest = package.manifest
    problem = await session.scalar(
        select(Problem).where(Problem.slug == manifest.id).with_for_update()
    )
    if problem is None:
        owner = await session.scalar(select(Problem.slug).where(Problem.number == manifest.number))
        if owner is not None:
            raise ImportRefusedError(
                [f"{package.name}: number {manifest.number} belongs to {owner!r}"]
            )
        problem = Problem(id=uuid7(), slug=manifest.id, number=manifest.number)
        session.add(problem)
        await session.flush()
    elif problem.number != manifest.number:
        raise ImportRefusedError(
            [f"{package.name}: number {manifest.number}, but the problem has {problem.number}"]
        )

    rows = await session.execute(
        select(ProblemVersion.version, ProblemVersion.id, ProblemVersion.content_hash).where(
            ProblemVersion.problem_id == problem.id
        )
    )
    versions = {number: (id, hash) for number, id, hash in rows}
    if manifest.version in versions:
        version_id, stored_hash = versions[manifest.version]
        if stored_hash != package.content_hash:
            raise ImportRefusedError(
                [
                    f"{package.name}: the version is already imported with content hash"
                    f" {stored_hash}, the package has {package.content_hash};"
                    " a published version is immutable, increase `version`"
                ]
            )
        outcome: Literal["created", "unchanged"] = "unchanged"
    else:
        latest = max(versions, default=0)
        if manifest.version < latest:
            raise ImportRefusedError([f"{package.name}: older than the imported version {latest}"])
        version_id = await _create_version(session, problem, package)
        outcome = "created"

    if publish:
        current = next(
            (n for n, (id, _) in versions.items() if id == problem.current_version_id), 0
        )
        if manifest.version < current:
            raise ImportRefusedError([f"{package.name}: older than the current version {current}"])
        problem.current_version_id = version_id
        problem.is_published = True
        await session.flush()
    return Imported(package, outcome, published=publish)


async def _create_version(session: AsyncSession, problem: Problem, package: Package) -> uuid.UUID:
    manifest = package.manifest
    version = ProblemVersion(
        id=uuid7(),
        problem_id=problem.id,
        version=manifest.version,
        content_hash=package.content_hash,
        language=manifest.language,
        kind=manifest.kind,
        title=manifest.title,
        difficulty=manifest.difficulty,
        tags=list(manifest.tags),
        statement_md=package.text(manifest.files.statement),
        template=package.text(manifest.files.template),
        changelog=manifest.changelog,
        interface=manifest.interface.model_dump(mode="json"),
        manifest=manifest.model_dump(mode="json", by_alias=True),
        package_uri=package.key,
        resource_class=manifest.resource_class,
        leaderboard_epoch=manifest.leaderboard_epoch,
    )
    session.add(version)
    await session.flush()
    for solution in manifest.reference.solutions if manifest.reference else []:
        session.add(
            ReferenceSolution(
                id=uuid7(),
                problem_version_id=version.id,
                title=solution.title,
                code=package.text(solution.file),
                explanation_md=package.text(solution.explanation) if solution.explanation else None,
            )
        )
    await session.flush()
    return version.id
