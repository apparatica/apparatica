"""Reading the leaderboard of a problem (FR-LB-01..04, T3.5): the entries that `ranking` keeps,
as pages show them — the leaderboard of the current version on the default toolchain profile.

- Rows. With `group=true` a row is a leader of a group with the count and the earliest 50 of its
  followers; with `group=false` every entry is a row, a follower right after its leader with the
  leader's place and `duplicate_of` (FR-LB-04).
- Order. `rank` is the order of the places: `sort_values`, then the time of sending, which does
  not split a place. Another `sort` orders by the time or by a metric of `columns` and then by the
  places; sorting never changes the places (FR-LB-01).
- Metrics of a solution are the numbers its stages of the formula and its synthesis and formal
  stages reported, `<stage key>.<metric>` (specs/05 §5); `columns` are the formula and then the
  other metrics of the first place.
- The reference shown with the leaderboard is the best reference solution by the formula; its
  metrics are public whatever the visibility of its code (FR-REF-01). The metrics of a reference
  solution are those of its latest accepted run on the default profile (FR-SYN-04,
  `apparatica.leaderboards.references`), the same public metrics as of a solution.
"""

import re
import uuid
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import (
    Numeric,
    Row,
    Select,
    SQLColumnExpression,
    and_,
    case,
    cast,
    func,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import UnaryExpression

from apparatica.auth.models import User
from apparatica.auth.schemas import UserRef
from apparatica.core.errors import ApiError, ErrorCode
from apparatica.leaderboards.models import LeaderboardEntry
from apparatica.leaderboards.ranking import BoardKey, current_key, default_profile
from apparatica.leaderboards.schemas import (
    DuplicateOf,
    GroupMember,
    LeaderboardRow,
    ProblemLeaderboard,
    ReferenceMetrics,
)
from apparatica.problems.models import Problem, ProblemVersion, ReferenceSolution
from apparatica.problems.progress import ACCEPTED
from apparatica.submissions.models import StageResult, Submission
from judge.core.leaderboard import sort_values
from judge.core.package import Leaderboard

GROUP_LIMIT = 50  # followers listed under a leader
# Types of the stages whose metrics anyone may see (specs/05 §5).
PUBLIC_METRIC_TYPES = ("synth", "formal")
METRIC_KEY = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")  # MetricKey of the schemas

type Metrics = dict[str, float]
type AnySelect = Select[*tuple[Any, ...]]

Entry = LeaderboardEntry
Leader = aliased(LeaderboardEntry, name="leader")
Author = aliased(User, name="author")
LeaderAuthor = aliased(User, name="leader_author")
# The place of an entry: a follower shows the place of its leader.
PLACE = func.coalesce(Entry.rank, Leader.rank)
# The order of the places: a follower right after its leader, followers by time.
PLACES: tuple[SQLColumnExpression[Any], ...] = (
    func.coalesce(Leader.sort_values, Entry.sort_values),
    func.coalesce(Leader.submitted_at, Entry.submitted_at),
    func.coalesce(Leader.id, Entry.id),
    Entry.group_leader_entry_id.is_not(None),
    Entry.submitted_at,
    Entry.id,
)


@dataclass(frozen=True)
class Board:
    """A published problem, its current version and the leaderboard pages show for it."""

    problem: Problem
    version: ProblemVersion
    formula: Leaderboard | None  # None: the problem has no leaderboard
    key: BoardKey | None  # None: no leaderboard, or no default profile of the language
    profile: str | None  # the default toolchain profile of the language

    @property
    def stages(self) -> list[str]:
        """Keys of the stages of the formula."""
        return stages_of(self.formula)


def formula_of(version: ProblemVersion) -> Leaderboard | None:
    """The formula of the leaderboard of a version; None: it has none."""
    leaderboard = version.manifest.get("leaderboard")
    return None if leaderboard is None else Leaderboard.model_validate(leaderboard)


def stages_of(formula: Leaderboard | None) -> list[str]:
    """Keys of the stages of the formula."""
    order = formula.order if formula is not None else []
    return list(dict.fromkeys(item.metric.split(".", 1)[0] for item in order))


async def find_board(session: AsyncSession, slug: str) -> Board | None:
    """The board of a published problem; None: no such problem."""
    found = (
        await session.execute(
            select(Problem, ProblemVersion)
            .join(ProblemVersion, ProblemVersion.id == Problem.current_version_id)
            .where(Problem.slug == slug, Problem.is_published)
        )
    ).one_or_none()
    if found is None:
        return None
    problem, version = found
    return await board_of(session, problem, version)


async def board_of(session: AsyncSession, problem: Problem, current: ProblemVersion) -> Board:
    formula = formula_of(current)
    key = await current_key(session, current)
    profile: str | None
    if key is not None:
        profile = key.toolchain_profile_id
    else:
        profile = await default_profile(session, current.language)
    return Board(problem, current, formula, key, profile)


def user_ref(user: User) -> UserRef:
    return UserRef(nick=user.nick, display_name=user.display_name, avatar_url=user.avatar_url)


async def metrics_of(
    session: AsyncSession, submission_ids: Collection[uuid.UUID], stages: Sequence[str]
) -> dict[uuid.UUID, Metrics]:
    """The public metrics of the submissions: numbers of the stages `stages` and of the stages
    of the types in PUBLIC_METRIC_TYPES."""
    found: dict[uuid.UUID, Metrics] = {submission_id: {} for submission_id in submission_ids}
    if not found:
        return found
    rows = await session.execute(
        select(StageResult.submission_id, StageResult.stage_key, StageResult.metrics).where(
            StageResult.submission_id.in_(found),
            or_(
                StageResult.stage_key.in_(stages),
                StageResult.stage_type.in_(PUBLIC_METRIC_TYPES),
            ),
        )
    )
    for submission_id, stage, metrics in rows:
        found[submission_id].update(
            numbers({f"{stage}.{name}": value for name, value in (metrics or {}).items()})
        )
    return found


def numbers(metrics: Mapping[str, object]) -> Metrics:
    """The numeric metrics with keys of the API (a bool is no number)."""
    return {
        key: value
        for key, value in metrics.items()
        if isinstance(value, int | float) and not isinstance(value, bool) and METRIC_KEY.match(key)
    }


def columns_of(formula: Leaderboard | None, best: Metrics | None) -> list[str]:
    """The formula, then the other metrics of the first place by name."""
    order = [item.metric for item in formula.order] if formula is not None else []
    return order + sorted(set(best or {}) - set(order))


def metric_value(
    statement: AnySelect, submission_id: SQLColumnExpression[uuid.UUID], metric: str
) -> tuple[AnySelect, SQLColumnExpression[Any]]:
    """Joins the stage result of the metric `<stage key>.<metric>` of the submission: the
    statement and the value, null when the stage did not report a number."""
    stage, name = metric.split(".", 1)
    result = aliased(StageResult)
    statement = statement.outerjoin(
        result, and_(result.submission_id == submission_id, result.stage_key == stage)
    )
    field = result.metrics[name]
    value = case((func.jsonb_typeof(field) == "number", cast(field.astext, Numeric)))
    return statement, value


def directed(value: SQLColumnExpression[Any], descending: bool) -> UnaryExpression[Any]:
    """Missing values last in both directions."""
    return (value.desc() if descending else value.asc()).nulls_last()


def check_sort(sort: str, columns: Sequence[str]) -> None:
    name = sort.removeprefix("-")
    if name not in ("rank", "submitted_at") and name not in columns:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            f"Cannot sort by {name!r}: rank, submitted_at or one of {', '.join(columns)}",
        )


def _board(statement: AnySelect, key: BoardKey) -> AnySelect:
    return (
        statement.select_from(Entry)
        .join(Author, Author.id == Entry.user_id)
        .outerjoin(Leader, Leader.id == Entry.group_leader_entry_id)
        .outerjoin(LeaderAuthor, LeaderAuthor.id == Leader.user_id)
        .where(*key.where())
    )


def _sorted(statement: AnySelect, sort: str) -> tuple[AnySelect, list[SQLColumnExpression[Any]]]:
    """The statement with what its order needs joined, and the order: `sort`, then the places."""
    if sort == "rank":
        return statement, list(PLACES)
    descending, name = sort.startswith("-"), sort.removeprefix("-")
    if name == "submitted_at":
        value: SQLColumnExpression[Any] = Entry.submitted_at
    else:
        statement, value = metric_value(statement, Entry.submission_id, name)
    return statement, [directed(value, descending), *PLACES]


# (entry, place, author, leader | None, author of the leader | None)
type Found = Row[*tuple[Any, ...]]


def _rows(key: BoardKey) -> AnySelect:
    return _board(select(Entry, PLACE, Author, Leader, LeaderAuthor), key)


async def best_entry(session: AsyncSession, key: BoardKey) -> Found | None:
    """The first place: the earliest entry of the lowest `sort_values`."""
    statement = _rows(key).where(Entry.group_leader_entry_id.is_(None)).order_by(*PLACES)
    return (await session.execute(statement.limit(1))).one_or_none()


async def best_metrics(session: AsyncSession, board: Board) -> Metrics | None:
    """The metrics of the first place; None: no entries or no leaderboard."""
    if board.key is None:
        return None
    best = await best_entry(session, board.key)
    if best is None:
        return None
    submission_id = best[0].submission_id
    return (await metrics_of(session, [submission_id], board.stages))[submission_id]


async def problem_leaderboard(
    session: AsyncSession,
    board: Board,
    *,
    viewer: uuid.UUID | None,
    group: bool,
    around_me: bool,
    sort: str,
    page: int,
    per_page: int,
) -> ProblemLeaderboard:
    """The page of the leaderboard; `viewer`: the signed-in user. NOT_FOUND: the problem has no
    leaderboard; VALIDATION_ERROR: `sort` names no column."""
    if board.key is None or board.formula is None:
        raise ApiError(ErrorCode.NOT_FOUND, f"Problem {board.problem.slug!r} has no leaderboard")
    key, formula = board.key, board.formula
    best = await best_entry(session, key)
    mine: Found | None = None
    if viewer is not None:
        mine = (await session.execute(_rows(key).where(Entry.user_id == viewer))).one_or_none()
    known = [found for found in (best, mine) if found is not None]
    metrics = await metrics_of(session, {found[0].submission_id for found in known}, board.stages)
    columns = columns_of(formula, metrics[best[0].submission_id] if best is not None else None)
    check_sort(sort, columns)

    leaders = Entry.group_leader_entry_id.is_(None)
    shown = [leaders] if group else []
    if around_me and mine is not None:
        follows = mine[0].group_leader_entry_id
        target = follows if group and follows is not None else mine[0].id
        numbered, order = _sorted(_board(select(Entry.id), key).where(*shown), sort)
        positions = numbered.add_columns(func.row_number().over(order_by=order).label("n"))
        found_n = positions.subquery()
        n = await session.scalar(select(found_n.c.n).where(found_n.c.id == target))
        if n is not None:
            page = (n - 1) // per_page + 1
    statement, order = _sorted(_rows(key).where(*shown), sort)
    rows: list[Found] = list(
        await session.execute(
            statement.order_by(*order).offset((page - 1) * per_page).limit(per_page)
        )
    )
    total, entries = (
        await session.execute(
            select(func.count().filter(leaders) if group else func.count(), func.count())
            .select_from(Entry)
            .where(*key.where())
        )
    ).one()

    every = [*rows, *known]
    metrics.update(
        await metrics_of(
            session,
            {found[0].submission_id for found in every} - set(metrics),
            board.stages,
        )
    )
    groups = (
        await _groups(session, {found[0].id for found in every if found[0].rank is not None})
        if group
        else {}
    )

    def row(found: Found) -> LeaderboardRow:
        entry, place, author, leader, leader_author = found
        count, members = groups.get(entry.id, (0, []))
        return LeaderboardRow(
            rank=place,
            solution_id=entry.submission_id,
            author=user_ref(author),
            metrics=metrics[entry.submission_id],
            submitted_at=entry.submitted_at,
            is_me=entry.user_id == viewer,
            duplicate_of=(
                DuplicateOf(solution_id=leader.submission_id, author=user_ref(leader_author))
                if leader is not None and leader_author is not None
                else None
            ),
            duplicates=count,
            group=members,
        )

    reference = await best_reference(session, board)
    return ProblemLeaderboard(
        items=[row(found) for found in rows],
        page=page,
        per_page=per_page,
        total=total,
        entries=entries,
        epoch=key.leaderboard_epoch,
        toolchain_profile=key.toolchain_profile_id,
        formula_version=key.formula_version,
        order=formula.order,
        columns=columns,
        best=row(best) if best is not None else None,
        reference=(
            ReferenceMetrics(title=reference[0], metrics=reference[1])
            if reference is not None
            else None
        ),
        me=row(mine) if mine is not None else None,
    )


async def _groups(
    session: AsyncSession, leader_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, list[GroupMember]]]:
    """Of each leader: the count of its followers and the earliest GROUP_LIMIT of them."""
    if not leader_ids:
        return {}
    follows = Entry.group_leader_entry_id.in_(leader_ids)
    counts = await session.execute(
        select(Entry.group_leader_entry_id, func.count())
        .where(follows)
        .group_by(Entry.group_leader_entry_id)
    )
    found: dict[uuid.UUID, tuple[int, list[GroupMember]]] = {
        leader: (count, []) for leader, count in counts if leader is not None
    }
    numbered = (
        select(
            Entry.group_leader_entry_id.label("leader"),
            Entry.submission_id,
            Entry.submitted_at,
            Entry.user_id,
            func.row_number()
            .over(partition_by=Entry.group_leader_entry_id, order_by=(Entry.submitted_at, Entry.id))
            .label("n"),
        )
        .where(follows)
        .subquery()
    )
    members = await session.execute(
        select(numbered.c.leader, numbered.c.submission_id, numbered.c.submitted_at, User)
        .join(User, User.id == numbered.c.user_id)
        .where(numbered.c.n <= GROUP_LIMIT)
        .order_by(numbered.c.leader, numbered.c.n)
    )
    for leader, submission_id, submitted_at, user in members:
        found[leader][1].append(
            GroupMember(solution_id=submission_id, author=user_ref(user), submitted_at=submitted_at)
        )
    return found


async def best_reference(session: AsyncSession, board: Board) -> tuple[str, Metrics] | None:
    """The title and the metrics of the best measured reference solution of the current version
    by the formula; the earlier one of equals. None: none measured, or no formula."""
    if board.formula is None:
        return None
    formula = board.formula
    references = (
        await session.execute(
            select(ReferenceSolution.id, ReferenceSolution.title)
            .where(ReferenceSolution.problem_version_id == board.version.id)
            .order_by(ReferenceSolution.id)
        )
    ).all()
    measured = await reference_metrics(
        session, board, [reference_id for reference_id, _ in references]
    )
    best: tuple[list[float], str, Metrics] | None = None
    for reference_id, title in references:
        metrics = measured.get(reference_id)
        if metrics is None or any(item.metric not in metrics for item in formula.order):
            continue
        values = sort_values(formula, metrics)
        if best is None or values < best[0]:
            best = (values, title, metrics)
    return None if best is None else (best[1], best[2])


async def reference_metrics(
    session: AsyncSession, board: Board, reference_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, Metrics]:
    """The public metrics of the reference solutions measured on the default profile: those of
    the latest accepted run of each (FR-SYN-04). A reference without one is missing."""
    if board.profile is None or not reference_ids:
        return {}
    runs = await session.execute(
        select(Submission.reference_solution_id, Submission.id)
        .where(
            Submission.reference_solution_id.in_(reference_ids),
            Submission.toolchain_profile_id == board.profile,
            Submission.status.in_(ACCEPTED),
        )
        .order_by(Submission.reference_solution_id, Submission.created_at.desc())
        .ext(distinct_on(Submission.reference_solution_id))
    )
    references = {run: reference for reference, run in runs if reference is not None}
    metrics = await metrics_of(session, references, board.stages)
    return {reference: metrics[run] for run, reference in references.items()}
