"""Reading the problem catalogue: published problems and the versions up to the current one.

A problem is visible once published; its versions up to the current one stay readable (old
submissions refer to them), newer imported ones are not visible until they are published.
"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import (
    ARRAY,
    ColumnElement,
    Float,
    Select,
    Text,
    cast,
    exists,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from apparatica.problems.models import Problem, ProblemStats, ProblemVersion, Tag
from apparatica.problems.schemas import (
    DifficultyTotal,
    PipelineInfo,
    PipelineStage,
    ProblemDetail,
    ProblemListItem,
    ProblemPage,
    Sort,
    TagList,
)
from apparatica.problems.schemas import Tag as TagSchema
from judge.core.package import Interface


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
) -> ProblemPage:
    """Filters of one kind are alternatives (any of the levels, any of the tags). Problems without
    an acceptance rate sort after the others in both directions."""
    conditions: list[ColumnElement[bool]] = []
    if difficulties:
        conditions.append(ProblemVersion.difficulty.in_(difficulties))
    if tags:
        conditions.append(ProblemVersion.tags.overlap(literal(list(tags), ARRAY(Text))))
    if q and q.strip():
        conditions.append(_matches(q.strip()))
    filtered = _current().where(*conditions)

    total = await session.scalar(select(func.count()).select_from(filtered.subquery()))
    # Levels unknown to the configuration sort after the known ones.
    level = func.coalesce(
        func.array_position(
            literal(list(difficulty_order), ARRAY(Text)), ProblemVersion.difficulty
        ),
        len(difficulty_order) + 1,
    )
    acceptance = cast(ProblemStats.accepted_authors, Float) / func.nullif(ProblemStats.authors, 0)
    keys = {"number": Problem.number, "difficulty": level, "acceptance": acceptance}
    key = keys[sort.removeprefix("-")]
    order = [(key.desc() if sort.startswith("-") else key.asc()).nulls_last(), Problem.number]
    rows = await session.execute(
        filtered.add_columns(acceptance)
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
        )
        for problem, version, rate in rows
    ]

    levels = await session.execute(
        _current()
        .with_only_columns(ProblemVersion.difficulty, func.count())
        .group_by(ProblemVersion.difficulty)
    )
    counts = {level: count for level, count in levels}
    progress = [
        DifficultyTotal(difficulty=key, total=counts.get(key, 0)) for key in difficulty_order
    ]
    return ProblemPage(
        items=items, page=page, per_page=per_page, total=total or 0, progress=progress
    )


async def get_problem(
    session: AsyncSession, slug: str, version: int | None = None
) -> ProblemDetail | None:
    """The current version, or the given one if it is not newer than the current one."""
    current = aliased(ProblemVersion)
    statement = (
        select(Problem, ProblemVersion, current.version)
        .join(current, current.id == Problem.current_version_id)
        .join(ProblemVersion, ProblemVersion.problem_id == Problem.id)
        .where(Problem.slug == slug, Problem.is_published)
    )
    if version is None:
        statement = statement.where(ProblemVersion.id == Problem.current_version_id)
    else:
        statement = statement.where(
            ProblemVersion.version == version, ProblemVersion.version <= current.version
        )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        return None
    problem, found, current_version = row
    manifest: dict[str, Any] = found.manifest
    return ProblemDetail(
        slug=problem.slug,
        number=problem.number,
        version=found.version,
        current_version=current_version,
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
        changelog=found.changelog,
        published_at=found.published_at,
    )


def _pipeline(manifest: dict[str, Any]) -> PipelineInfo:
    stages, practice = manifest["stages"], manifest["pipelines"]["practice"]

    def describe(keys: list[str]) -> list[PipelineStage]:
        return [PipelineStage(key=key, type=stages[key]["type"]) for key in keys]

    return PipelineInfo(run=describe(practice["run"]), submit=describe(practice["submit"]))


def _tests(manifest: dict[str, Any]) -> dict[str, int]:
    tests: dict[str, int] = {}
    for testbench in manifest.get("testbenches", []):
        for group, count in testbench["groups"].items():
            tests[group] = tests.get(group, 0) + count
    return tests
