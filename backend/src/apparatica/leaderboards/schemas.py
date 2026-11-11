"""Schemas of leaderboards, public solutions and reference solutions (specs/05 §3, phase 3).

Metrics are keyed `<stage key>.<metric>`, as `leaderboard.order` of the problem names them
(`synth.critical_path_ns`): the core knows stages and their metric schemas, not the language.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from apparatica.auth.schemas import UserRef
from apparatica.submissions.schemas import LeaderboardPlacement
from judge.core.package import LeaderboardKey
from judge.core.stage import ParamSet, StageStatus

MetricKey = Annotated[
    str, Field(pattern=r"^[a-z_]+\.[a-z0-9_]+$", examples=["synth.critical_path_ns"])
]
Metrics = Annotated[
    dict[MetricKey, float],
    Field(
        description="Metrics by `<stage key>.<metric>`, rounded to the precision of the tool",
        examples=[{"synth.critical_path_ns": 0.84, "synth.area_um2": 836.4, "synth.cells": 187}],
    ),
]
SolutionStatus = Literal["accepted", "accepted_with_warnings"]


class ProblemRef(BaseModel):
    slug: str = Field(examples=["sync-fifo"])
    number: int
    title: str
    difficulty: str = Field(description="Key of the difficulty levels of GET /config")


class DuplicateOf(BaseModel):
    """The earlier solution with the same normalized syntax tree, which holds the place
    (FR-LB-04); a match is no violation and costs nothing."""

    solution_id: uuid.UUID
    author: UserRef


class GroupMember(BaseModel):
    """A later solution with the same normalized syntax tree as the row: no place of its own."""

    solution_id: uuid.UUID
    author: UserRef
    submitted_at: datetime


class LeaderboardRow(BaseModel):
    """An entry: the best solution of an author (FR-LB-01, FR-LB-02)."""

    rank: int = Field(ge=1, description="Equal metrics share a place (1, 2, 2, 4)")
    solution_id: uuid.UUID
    author: UserRef
    metrics: Metrics
    submitted_at: datetime
    is_me: bool = Field(description="The entry of the signed-in user")
    duplicate_of: DuplicateOf | None = Field(
        description="The row is a later duplicate and shows its leader's rank; with group=true"
        " only `me` can be one"
    )
    duplicates: int = Field(
        ge=0, description="With group=true: later solutions with the same syntax tree"
    )
    group: list[GroupMember] = Field(
        description="With group=true: the earliest 50 of them, oldest first; empty otherwise"
    )


class ReferenceMetrics(BaseModel):
    title: str
    metrics: Metrics


class ProblemLeaderboard(BaseModel):
    """The leaderboard of a problem in its current epoch on the default toolchain profile."""

    items: list[LeaderboardRow]
    page: int
    per_page: int
    total: int = Field(description="Rows to page through: with group=true, without duplicates")
    entries: int = Field(description="Authors in the leaderboard: M of «place N of M»")
    epoch: int = Field(description="leaderboard_epoch of the current version")
    toolchain_profile: str = Field(examples=["sv-2026.10.2"])
    formula_version: int
    order: list[LeaderboardKey] = Field(description="The formula: the order of the places")
    columns: list[MetricKey] = Field(
        description="Metrics of the rows to show: the formula first, then the other metrics of"
        " its stages"
    )
    best: LeaderboardRow | None = Field(description="First place; null: no entries yet")
    reference: ReferenceMetrics | None = Field(
        description="The best reference solution by the formula; null: none or not measured yet"
        " (FR-SYN-04). Its metrics are public whatever reference.visibility says"
    )
    me: LeaderboardRow | None = Field(
        description="The entry of the signed-in user, wherever it is; null: a guest or no entry"
    )


class SolutionSummary(BaseModel):
    """A public solution: an accepted Submit of a signed-in user (specs/04 §6)."""

    id: uuid.UUID = Field(description="Id of the submission")
    problem: ProblemRef
    version: int = Field(description="Version of the problem the solution was checked on")
    author: UserRef
    status: SolutionStatus
    metrics: Metrics = Field(description="Empty without a synthesis stage")
    rank: int | None = Field(
        description="Place in the current leaderboard if this solution is its author's entry"
    )
    duplicate_of: DuplicateOf | None
    submitted_at: datetime


class SolutionPage(BaseModel):
    items: list[SolutionSummary]
    page: int
    per_page: int
    total: int
    code_locked: bool = Field(
        description="The visitor has no accepted Submit of the problem, so the code of others"
        " is closed (FR-SOL-02): GET /solutions/{id} gives no code"
    )


class ProfileRating(BaseModel):
    """The place in the global leaderboard (FR-LB-05)."""

    rank: int
    total: int = Field(description="Users with points")
    points: int
    week_delta: int | None = Field(
        description="Places gained in 7 days (negative: lost); null: not ranked a week ago"
    )


class BestPlace(BaseModel):
    """A place in the leaderboard of a problem, from the best (FR-USR-04)."""

    problem: ProblemRef
    rank: int
    entries: int = Field(description="Authors in that leaderboard")
    solution_id: uuid.UUID = Field(description="The solution that holds the place")
    order: list[LeaderboardKey] = Field(description="The formula of that leaderboard")


class UserSolutionPage(BaseModel):
    """Public solutions of a user, newest first (FR-USR-04)."""

    items: list[SolutionSummary]
    page: int
    per_page: int
    total: int


class TestCount(BaseModel):
    passed: int
    total: int = Field(description="Open and hidden tests together")


class PublicStage(BaseModel):
    """A stage of a public solution: what anyone may see (specs/05 §5)."""

    key: str = Field(examples=["synth"], description="Key of the stage instance")
    type: str = Field(examples=["synth"])
    param_set: ParamSet | None = Field(
        description="As in the submission: null at the primary parameter set only"
    )
    status: StageStatus
    metrics_schema: str | None = Field(examples=["synth/v1"])
    metrics: dict[str, object] = Field(
        description="Only of synthesis and formal stages; empty for the others"
    )
    tests: TestCount | None = Field(description="Of simulation stages: counts, no test data")


class SolutionAuthor(UserRef):
    created_at: datetime
    solved: int = Field(description="Problems the author solved")


class Solution(SolutionSummary):
    """A public solution page (FR-SOL-01)."""

    author: SolutionAuthor
    language: str = Field(examples=["systemverilog"])
    toolchain_profile: str
    code: str | None = Field(description="Null while code_locked")
    code_locked: bool = Field(
        description="The visitor has no accepted Submit of the problem (FR-SOL-02); the author"
        " sees their own code"
    )
    stages: list[PublicStage] = Field(description="In pipeline order")
    placement: LeaderboardPlacement | None = Field(
        description="Place of the author's entry if this solution holds it or duplicates it"
    )
    order: list[LeaderboardKey] = Field(
        description="The formula of the leaderboard; empty without one"
    )
    best: Metrics | None = Field(description="Of the first place, to compare with")
    reference: Metrics | None = Field(description="Of the best reference solution")


class ReferenceSolution(BaseModel):
    title: str
    code: str
    explanation_md: str | None = Field(description="The microarchitecture, in Markdown")
    metrics: Metrics | None = Field(
        description="On the default toolchain profile; null until measured (FR-SYN-04)"
    )


class ReferencePage(BaseModel):
    """Reference solutions of the current version (FR-REF-01)."""

    version: int
    visibility: Literal["after_accepted", "public"]
    solutions: list[ReferenceSolution]


class RatingRow(BaseModel):
    """A user in the global leaderboard (FR-LB-05)."""

    rank: int = Field(
        ge=1, description="Equal points: whoever reached them first ranks higher (ADR-0006)"
    )
    user: UserRef
    points: int
    solved: dict[str, int] = Field(
        description="Solved problems by the difficulty keys of GET /config"
    )
    week_delta: int | None = Field(
        description="Places gained in 7 days (negative: lost); null: not ranked a week ago"
    )
    is_me: bool


class PointsFormula(BaseModel):
    """How points are counted (`config/rating.yaml`, decision ОВ-4)."""

    version: int
    solved: dict[str, int] = Field(
        description="Points for a solved problem by the difficulty keys of GET /config",
        examples=[{"easy": 1, "medium": 3, "hard": 6}],
    )
    places: list[int] = Field(
        description="Bonus for place 1, 2, ... of a problem leaderboard; a shared place gives it"
        " to each holder, a solution matching an earlier one holds no place",
        examples=[[3, 2, 1]],
    )


class GlobalLeaderboard(BaseModel):
    """Users by points for all time (FR-LB-05): points per solved published problem by its level
    and a bonus for places of problem leaderboards (`formula`, ADR-0006)."""

    items: list[RatingRow]
    page: int
    per_page: int
    total: int = Field(description="Users with points")
    formula: PointsFormula
    me: RatingRow | None = Field(description="Null: a guest or no points yet")
    around_me: list[RatingRow] = Field(
        description="Up to two rows above and below mine when mine is not on this page,"
        " for the gap «· · ·» (FR-LB-05)"
    )
