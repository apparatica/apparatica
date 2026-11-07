"""Public solutions and reference solutions (FR-SOL-01..03, FR-REF-01, T3.5).

A public solution is an accepted Submit of a signed-in user (`submissions.is_public`); its id is
the id of the submission. A solution or a user hidden by a moderator is public no more: for
nobody, the author included (FR-ADM-03). Metrics, author and place are for everyone, the code of
others opens after the visitor's own accepted Submit of the problem (ОВ-2, FR-SOL-02):

- the author always sees their code, moderators and administrators see every code;
- a signed-in visitor counts their own Submits, a guest those of the guest cookie, like the list
  of their submissions (`Author.owns`); a guest Submit moved to an account (phase 4) belongs to
  the account.

Reference solutions of the current version follow `reference.visibility` of the problem:
`after_accepted` (the default) with the same rule, `public` for everyone, `hidden` for nobody.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, SQLColumnExpression, and_, exists, false, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from apparatica.auth.models import User
from apparatica.core.errors import ApiError, ErrorCode
from apparatica.leaderboards.boards import (
    PLACE,
    PUBLIC_METRIC_TYPES,
    AnySelect,
    Board,
    Entry,
    Leader,
    LeaderAuthor,
    best_metrics,
    best_reference,
    board_of,
    check_sort,
    columns_of,
    directed,
    formula_of,
    metric_value,
    metrics_of,
    reference_metrics,
    stages_of,
    user_ref,
)
from apparatica.leaderboards.ranking import current_boards, in_board, placement_of
from apparatica.leaderboards.schemas import (
    DuplicateOf,
    ProblemRef,
    PublicStage,
    ReferencePage,
    Solution,
    SolutionAuthor,
    SolutionPage,
    SolutionSummary,
    TestCount,
    UserSolutionPage,
)
from apparatica.leaderboards.schemas import ReferenceSolution as ReferenceSchema
from apparatica.problems.models import Problem, ProblemVersion, ReferenceSolution, UserProblemStatus
from apparatica.problems.progress import ACCEPTED
from apparatica.submissions.models import StageResult, Submission
from apparatica.submissions.quotas import Author
from judge.core.package import Reference
from judge.core.stage import StageSummary

STAFF = ("moderator", "admin")  # see every code (specs/04 §6)


def shown() -> ColumnElement[bool]:
    """A public solution nobody hid, of an author nobody hid; `User` is the author."""
    return and_(Submission.is_public, Submission.is_hidden.is_(False), User.is_hidden.is_(False))


@dataclass(frozen=True)
class Visitor:
    """Who asks: the signed-in user, else the guest of the cookie, else nobody."""

    author: Author
    role: str | None = None  # of the signed-in user

    @property
    def user_id(self) -> uuid.UUID | None:
        return self.author.user_id


async def code_open(session: AsyncSession, problem_id: uuid.UUID, visitor: Visitor) -> bool:
    """Whether the code of others of the problem is open to the visitor: staff, or their own
    accepted Submit of any version of the problem."""
    if visitor.role in STAFF:
        return True
    solved = await session.scalar(
        select(
            exists().where(
                visitor.author.owns(),
                Submission.kind == "submit",
                Submission.status.in_(ACCEPTED),
                Submission.problem_version_id.in_(
                    select(ProblemVersion.id).where(ProblemVersion.problem_id == problem_id)
                ),
            )
        )
    )
    return bool(solved)


def _summaries(board: Board) -> AnySelect:
    """Public solutions of the problem with their version, author and entry in the leaderboard
    of the board, if any."""
    in_board = (
        and_(Entry.submission_id == Submission.id, *board.key.where())
        if board.key is not None
        else false()
    )
    return (
        select(Submission, ProblemVersion.version, User, PLACE, Leader, LeaderAuthor)
        .join(ProblemVersion, ProblemVersion.id == Submission.problem_version_id)
        .join(User, User.id == Submission.user_id)
        .outerjoin(Entry, in_board)
        .outerjoin(Leader, Leader.id == Entry.group_leader_entry_id)
        .outerjoin(LeaderAuthor, LeaderAuthor.id == Leader.user_id)
        .where(ProblemVersion.problem_id == board.problem.id, shown())
    )


def _sorted(
    statement: AnySelect, board: Board, sort: str
) -> tuple[AnySelect, list[SQLColumnExpression[Any]]]:
    """`rank`: by the formula of the leaderboard, solutions without its metrics last; else by
    `sort` and then by the formula. Equals by the time of sending."""
    by_formula: list[SQLColumnExpression[Any]] = []
    for item in board.formula.order if board.formula is not None else []:
        statement, value = metric_value(statement, Submission.id, item.metric)
        by_formula.append(directed(value, item.dir == "desc"))
    order = [*by_formula, Submission.created_at, Submission.id]
    if sort == "rank":
        return statement, order
    descending, name = sort.startswith("-"), sort.removeprefix("-")
    if name == "submitted_at":
        value = Submission.created_at
    else:
        statement, value = metric_value(statement, Submission.id, name)
    return statement, [directed(value, descending), *order]


def _ref(board: Board) -> ProblemRef:
    return ProblemRef(
        slug=board.problem.slug,
        number=board.problem.number,
        title=board.version.title,
        difficulty=board.version.difficulty,
    )


async def _summarize(
    session: AsyncSession, board: Board, rows: list[Any]
) -> list[tuple[SolutionSummary, Submission, User]]:
    metrics = await metrics_of(session, {row[0].id for row in rows}, board.stages)
    problem = _ref(board)
    found = []
    for submission, version, author, place, leader, leader_author in rows:
        summary = _summary(
            submission,
            version,
            author,
            place,
            leader,
            leader_author,
            problem,
            metrics[submission.id],
        )
        found.append((summary, submission, author))
    return found


def _summary(
    submission: Submission,
    version: int,
    author: User,
    place: int | None,
    leader: Entry | None,
    leader_author: User | None,
    problem: ProblemRef,
    metrics: dict[str, float],
) -> SolutionSummary:
    return SolutionSummary(
        id=submission.id,
        problem=problem,
        version=version,
        author=user_ref(author),
        status=submission.status,  # type: ignore[arg-type]  # public: accepted ones
        metrics=metrics,
        rank=place,
        duplicate_of=(
            DuplicateOf(solution_id=leader.submission_id, author=user_ref(leader_author))
            if leader is not None and leader_author is not None
            else None
        ),
        submitted_at=submission.created_at,
    )


async def list_solutions(
    session: AsyncSession, board: Board, visitor: Visitor, *, sort: str, page: int, per_page: int
) -> SolutionPage:
    """Public solutions of every version of the problem (FR-SOL-03). VALIDATION_ERROR: `sort`
    names no column of the leaderboard."""
    check_sort(sort, columns_of(board.formula, await best_metrics(session, board)))
    statement, order = _sorted(_summaries(board), board, sort)
    rows = list(
        await session.execute(
            statement.order_by(*order).offset((page - 1) * per_page).limit(per_page)
        )
    )
    total = await session.scalar(
        select(func.count())
        .select_from(Submission)
        .join(ProblemVersion, ProblemVersion.id == Submission.problem_version_id)
        .join(User, User.id == Submission.user_id)
        .where(ProblemVersion.problem_id == board.problem.id, shown())
    )
    return SolutionPage(
        items=[summary for summary, _, _ in await _summarize(session, board, rows)],
        page=page,
        per_page=per_page,
        total=total or 0,
        code_locked=not await code_open(session, board.problem.id, visitor),
    )


def _of_user(user_id: uuid.UUID) -> ColumnElement[bool]:
    return and_(Submission.user_id == user_id, shown(), Problem.is_published)


async def user_solutions(
    session: AsyncSession, user_id: uuid.UUID, *, page: int, per_page: int
) -> UserSolutionPage:
    """Public solutions of the user on published problems, newest first (FR-USR-04), each with
    its place in the leaderboard pages show now, as in the list of the problem."""
    boards = current_boards()
    current = aliased(ProblemVersion, name="current")
    rows = list(
        await session.execute(
            select(Submission, ProblemVersion.version, User, PLACE, Leader, LeaderAuthor)
            .add_columns(Problem, current)
            .join(ProblemVersion, ProblemVersion.id == Submission.problem_version_id)
            .join(Problem, Problem.id == ProblemVersion.problem_id)
            .join(current, current.id == Problem.current_version_id)
            .join(User, User.id == Submission.user_id)
            .outerjoin(boards, boards.c.problem_id == Problem.id)
            .outerjoin(Entry, and_(Entry.submission_id == Submission.id, in_board(boards)))
            .outerjoin(Leader, Leader.id == Entry.group_leader_entry_id)
            .outerjoin(LeaderAuthor, LeaderAuthor.id == Leader.user_id)
            .where(_of_user(user_id))
            .order_by(Submission.created_at.desc(), Submission.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    )
    # The metrics of the stages of each formula, problem by problem.
    by_stages: dict[tuple[str, ...], set[uuid.UUID]] = {}
    for row in rows:
        stages = tuple(stages_of(formula_of(row[-1])))
        by_stages.setdefault(stages, set()).add(row[0].id)
    metrics: dict[uuid.UUID, dict[str, float]] = {}
    for stages, ids in by_stages.items():
        metrics.update(await metrics_of(session, ids, stages))
    items = [
        _summary(
            submission,
            version,
            author,
            place,
            leader,
            leader_author,
            ProblemRef(
                slug=problem.slug,
                number=problem.number,
                title=latest.title,
                difficulty=latest.difficulty,
            ),
            metrics[submission.id],
        )
        for submission, version, author, place, leader, leader_author, problem, latest in rows
    ]
    return UserSolutionPage(
        items=items,
        page=page,
        per_page=per_page,
        total=await count_user_solutions(session, user_id),
    )


async def count_user_solutions(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Public solutions of the user on published problems."""
    total = await session.scalar(
        select(func.count())
        .select_from(Submission)
        .join(ProblemVersion, ProblemVersion.id == Submission.problem_version_id)
        .join(Problem, Problem.id == ProblemVersion.problem_id)
        .join(User, User.id == Submission.user_id)
        .where(_of_user(user_id))
    )
    return total or 0


async def get_solution(
    session: AsyncSession, solution_id: uuid.UUID, visitor: Visitor
) -> Solution | None:
    """A public solution of a published problem; None: there is none with this id."""
    problem = await session.scalar(
        select(Problem)
        .join(ProblemVersion, ProblemVersion.problem_id == Problem.id)
        .join(Submission, Submission.problem_version_id == ProblemVersion.id)
        .join(User, User.id == Submission.user_id)
        .where(Submission.id == solution_id, shown(), Problem.is_published)
    )
    if problem is None or problem.current_version_id is None:
        return None
    current = await session.get(ProblemVersion, problem.current_version_id)
    assert current is not None  # a foreign key
    board = await board_of(session, problem, current)
    rows = list(await session.execute(_summaries(board).where(Submission.id == solution_id)))
    [(summary, submission, author)] = await _summarize(session, board, rows)
    version = await session.get(ProblemVersion, submission.problem_version_id)
    assert version is not None  # a foreign key
    stages = await session.scalars(
        select(StageResult)
        .where(StageResult.submission_id == solution_id)
        .order_by(StageResult.ordinal)
    )
    solved = await session.scalar(
        select(func.count())
        .select_from(UserProblemStatus)
        .join(Problem, Problem.id == UserProblemStatus.problem_id)
        .where(
            UserProblemStatus.user_id == author.id,
            UserProblemStatus.status == "solved",
            Problem.is_published,
        )
    )
    own = visitor.user_id is not None and visitor.user_id == submission.user_id
    locked = not own and not await code_open(session, problem.id, visitor)
    placement = await placement_of(session, submission)
    reference = await best_reference(session, board)
    return Solution(
        **summary.model_dump(exclude={"author"}),
        author=SolutionAuthor(
            **summary.author.model_dump(), created_at=author.created_at, solved=solved or 0
        ),
        language=version.language,
        toolchain_profile=submission.toolchain_profile_id,
        code=None if locked else submission.code,
        code_locked=locked,
        stages=[public_stage(stage) for stage in stages],
        placement=placement if placement is not None and placement.is_best else None,
        order=board.formula.order if board.formula is not None else [],
        best=await best_metrics(session, board),
        reference=reference[1] if reference is not None else None,
    )


def public_stage(stage: StageResult) -> PublicStage:
    """What anyone may see of a stage (specs/05 §5): metrics of synthesis and formal stages, the
    counts of the tests of a simulation, no test data."""
    summary = StageSummary.model_validate(stage.summary or {})
    hidden = summary.hidden_tests
    tests = None
    if summary.tests or hidden is not None:
        tests = TestCount(
            passed=sum(test.status == "passed" for test in summary.tests)
            + (hidden.passed if hidden else 0),
            total=len(summary.tests) + (hidden.total if hidden else 0),
        )
    return PublicStage(
        key=stage.stage_key,
        type=stage.stage_type,
        status=stage.status,  # type: ignore[arg-type]  # a stage_status value
        metrics_schema=stage.metrics_schema,
        metrics=(stage.metrics or {}) if stage.stage_type in PUBLIC_METRIC_TYPES else {},
        tests=tests,
    )


async def get_reference(session: AsyncSession, board: Board, visitor: Visitor) -> ReferencePage:
    """Reference solutions of the current version (FR-REF-01). NOT_FOUND: none or hidden;
    REFERENCE_LOCKED: `after_accepted` and the visitor has no accepted Submit of the problem."""
    reference = Reference.model_validate(board.version.manifest.get("reference") or {})
    visibility = reference.visibility or "after_accepted"
    if visibility == "hidden" or not reference.solutions:
        raise ApiError(
            ErrorCode.NOT_FOUND, f"Problem {board.problem.slug!r} shows no reference solutions"
        )
    if visibility == "after_accepted" and not await code_open(session, board.problem.id, visitor):
        raise ApiError(
            ErrorCode.REFERENCE_LOCKED, "The reference solutions open after your accepted Submit"
        )
    solutions = (
        await session.scalars(
            select(ReferenceSolution)
            .where(ReferenceSolution.problem_version_id == board.version.id)
            .order_by(ReferenceSolution.id)
        )
    ).all()
    measured = await reference_metrics(session, board, [solution.id for solution in solutions])
    return ReferencePage(
        version=board.version.version,
        visibility=visibility,
        solutions=[
            ReferenceSchema(
                title=solution.title,
                code=solution.code,
                explanation_md=solution.explanation_md,
                metrics=measured.get(solution.id),
            )
            for solution in solutions
        ],
    )
