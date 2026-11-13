"""Reading the problem catalogue: published problems and the versions up to the current one.

A problem is visible once published; its versions up to the current one stay readable (old
submissions refer to them), newer imported ones are not visible until they are published.
"""

import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    ColumnElement,
    Float,
    Select,
    Text,
    and_,
    cast,
    exists,
    func,
    literal,
    null,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from apparatica.problems import assets
from apparatica.problems.models import (
    Problem,
    ProblemStats,
    ProblemVersion,
    Tag,
    UserProblemStatus,
)
from apparatica.problems.schemas import (
    DifficultyTotal,
    LeaderboardFormula,
    PipelineInfo,
    PipelineStage,
    ProblemDetail,
    ProblemListItem,
    ProblemPage,
    ProblemVersionDetail,
    ReferenceInfo,
    Sort,
    TagList,
)
from apparatica.problems.schemas import Tag as TagSchema
from judge.core.package import PRIMARY_SET, Interface, split_instance_key
from judge.core.package import Problem as Package
from judge.core.stage import ParamSet


async def list_tags(session: AsyncSession) -> TagList:
    rows = await session.execute(select(Tag.slug, Tag.title).order_by(Tag.sort, Tag.slug))
    return TagList([TagSchema(slug=slug, title=title) for slug, title in rows])


def _current() -> Select[Problem, ProblemVersion]:
    return (
        select(Problem, ProblemVersion)
        .join(ProblemVersion, ProblemVersion.id == Problem.current_version_id)
        .where(Problem.is_published)
    )


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _matches(q: str) -> ColumnElement[bool]:
    """The title or one of the tags (slug or title) contains the text, case-insensitively."""
    pattern = f"%{_escape_like(q)}%"
    tag = aliased(Tag)
    return or_(
        ProblemVersion.title.ilike(pattern, escape="\\"),
        exists().where(
            tag.slug == func.any(ProblemVersion.tags),
            or_(tag.slug.ilike(pattern, escape="\\"), tag.title.ilike(pattern, escape="\\")),
        ),
    )


async def list_problems(
    session: AsyncSession,
    difficulty_order: Sequence[str],
    *,
    difficulties: Sequence[str],
    tags: Sequence[str],
    q: str | None,
    sort: Sort,
    page: int,
    per_page: int,
    user_id: uuid.UUID | None = None,
    statuses: Sequence[str] = (),
) -> ProblemPage:
    """Filters of one kind are alternatives (any of the levels, any of the tags, any of the
    `statuses` of the user). Problems without an acceptance rate sort after the others in both
    directions. With `user_id` the problems and the progress carry the statuses of the user."""
    current = _current()
    status: ColumnElement[Any] = null()  # the guest's are in the browser
    solved: ColumnElement[Any] = null()
    if user_id is not None:
        mine = and_(
            UserProblemStatus.problem_id == Problem.id, UserProblemStatus.user_id == user_id
        )
        current = current.outerjoin(UserProblemStatus, mine)
        status = func.coalesce(UserProblemStatus.status, "not_started")
        solved = func.count().filter(UserProblemStatus.status == "solved")
    conditions: list[ColumnElement[bool]] = []
    if statuses:
        conditions.append(status.in_(statuses))
    if difficulties:
        conditions.append(ProblemVersion.difficulty.in_(difficulties))
    if tags:
        conditions.append(ProblemVersion.tags.overlap(literal(list(tags), ARRAY(Text))))
    if q and q.strip():
        conditions.append(_matches(q.strip()))
    filtered = current.where(*conditions)

    total = await session.scalar(select(func.count()).select_from(filtered.subquery()))
    # Levels unknown to the configuration sort after the known ones.
    level = func.coalesce(
        func.array_position(
            literal(list(difficulty_order), ARRAY(Text)), ProblemVersion.difficulty
        ),
        len(difficulty_order) + 1,
    )
    acceptance = _acceptance()
    keys = {"number": Problem.number, "difficulty": level, "acceptance": acceptance}
    key = keys[sort.removeprefix("-")]
    order = [(key.desc() if sort.startswith("-") else key.asc()).nulls_last(), Problem.number]
    rows = await session.execute(
        filtered.add_columns(acceptance, status)
        .outerjoin(ProblemStats, ProblemStats.problem_id == Problem.id)
        .order_by(*order)
        .limit(per_page)
        .offset((page - 1) * per_page)
    )
    items = [
        ProblemListItem(
            slug=problem.slug,
            number=problem.number,
            title=version.title,
            difficulty=version.difficulty,
            tags=version.tags,
            acceptance=None if rate is None else round(rate, 4),
            status=problem_status,
        )
        for problem, version, rate, problem_status in rows
    ]

    levels = await session.execute(
        current.with_only_columns(ProblemVersion.difficulty, func.count(), solved).group_by(
            ProblemVersion.difficulty
        )
    )
    counts = {level: (count, done) for level, count, done in levels}
    empty = (0, None if user_id is None else 0)
    progress = [
        DifficultyTotal(difficulty=key, total=count, solved=done)
        for key in difficulty_order
        for count, done in [counts.get(key, empty)]
    ]
    return ProblemPage(
        items=items, page=page, per_page=per_page, total=total or 0, progress=progress
    )


def _acceptance() -> ColumnElement[float | Decimal]:
    """Accepted authors of the problem among the authors with a judged Submit; null without one."""
    return cast(ProblemStats.accepted_authors, Float) / func.nullif(ProblemStats.authors, 0)


async def get_problem(session: AsyncSession, slug: str) -> ProblemDetail | None:
    """The current version of a published problem and its acceptance rate."""
    row = (
        await session.execute(
            select(Problem, ProblemVersion, _acceptance())
            .join(ProblemVersion, ProblemVersion.id == Problem.current_version_id)
            .outerjoin(ProblemStats, ProblemStats.problem_id == Problem.id)
            .where(Problem.slug == slug, Problem.is_published)
        )
    ).one_or_none()
    if row is None:
        return None
    problem, version, rate = row
    detail = _detail(problem, version)
    acceptance = None if rate is None else round(float(rate), 4)
    return ProblemDetail(**detail.model_dump(), acceptance=acceptance)


async def get_problem_version(
    session: AsyncSession, slug: str, version: int
) -> ProblemVersionDetail | None:
    """A version of a published problem, if it is not newer than the current one."""
    row = (await session.execute(_visible_version(slug, version))).one_or_none()
    if row is None:
        return None
    problem, found = row
    return _detail(problem, found)


async def asset_key(session: AsyncSession, slug: str, version: int, path: str) -> str | None:
    """Storage key of a file of a version that `get_problem_version` shows; whether the package
    has the file is for the storage to say."""
    row = (await session.execute(_visible_version(slug, version))).one_or_none()
    if row is None:
        return None
    _, found = row
    return assets.asset_key(slug, version, found.content_hash, path)


def _visible_version(slug: str, version: int) -> Select[Problem, ProblemVersion]:
    current = aliased(ProblemVersion)
    return (
        select(Problem, ProblemVersion)
        .join(current, current.id == Problem.current_version_id)
        .join(ProblemVersion, ProblemVersion.problem_id == Problem.id)
        .where(
            Problem.slug == slug,
            Problem.is_published,
            ProblemVersion.version == version,
            ProblemVersion.version <= current.version,
        )
    )


def _detail(problem: Problem, found: ProblemVersion) -> ProblemVersionDetail:
    manifest: dict[str, Any] = found.manifest
    return ProblemVersionDetail(
        slug=problem.slug,
        number=problem.number,
        version=found.version,
        title=found.title,
        difficulty=found.difficulty,
        tags=found.tags,
        language=found.language,
        resource_class=found.resource_class,
        statement_md=found.statement_md,
        template=found.template,
        top=manifest["top"],
        interface=Interface.model_validate(found.interface),
        pipeline=_pipeline(manifest),
        tests=_tests(manifest),
        leaderboard=_leaderboard(manifest),
        reference=_reference(manifest),
        changelog=found.changelog,
        published_at=found.published_at,
    )


def _pipeline(manifest: dict[str, Any]) -> PipelineInfo:
    """The stage instances of Run and Submit as the judge runs them (ADR-0014)."""
    package = Package.model_validate(manifest)
    interface = package.interface

    def describe(keys: list[str]) -> list[PipelineStage]:
        described = []
        for key in package.instance_keys(keys):
            stage_key, set_id = split_instance_key(key)
            param_set = None
            if package.stage_param_sets(stage_key) != [PRIMARY_SET]:
                param_set = ParamSet(id=set_id, values=interface.param_set_values(set_id))
            stage_type = package.stages[stage_key].type
            described.append(PipelineStage(key=key, type=stage_type, param_set=param_set))
        return described

    practice = package.pipelines.practice
    return PipelineInfo(run=describe(practice.run), submit=describe(practice.submit))


def _leaderboard(manifest: dict[str, Any]) -> LeaderboardFormula | None:
    leaderboard = manifest.get("leaderboard")
    return None if leaderboard is None else LeaderboardFormula.model_validate(leaderboard)


def _reference(manifest: dict[str, Any]) -> ReferenceInfo | None:
    reference = manifest.get("reference") or {}
    visibility = reference.get("visibility") or "after_accepted"
    solutions = len(reference.get("solutions", []))
    if visibility == "hidden" or not solutions:
        return None
    return ReferenceInfo.model_validate({"visibility": visibility, "solutions": solutions})


def _tests(manifest: dict[str, Any]) -> dict[str, int]:
    tests: dict[str, int] = {}
    for testbench in manifest.get("testbenches", []):
        for group, count in testbench["groups"].items():
            tests[group] = tests.get(group, 0) + count
    return tests
