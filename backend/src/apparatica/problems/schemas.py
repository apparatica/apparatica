"""Response schemas of the problem catalogue (specs/05 §3, phase 0).

Per-user fields (status, progress solved) arrive with users in phase 2; the interface
of a problem is the `interface` model of the package manifest, as the statement shows it.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, RootModel

from judge.core.package import Interface

Sort = Literal["number", "-number", "difficulty", "-difficulty", "acceptance", "-acceptance"]


class Tag(BaseModel):
    slug: str = Field(examples=["fifo"])
    title: str = Field(examples=["FIFO"])


TagList = RootModel[list[Tag]]


class ProblemListItem(BaseModel):
    slug: str = Field(examples=["sync-fifo"])
    number: int
    title: str
    difficulty: str = Field(description="Key of the difficulty levels of GET /config")
    tags: list[str] = Field(description="Tag slugs, titles in GET /tags")
    acceptance: float | None = Field(
        ge=0,
        le=1,
        examples=[0.78],
        description="Share of the authors with a judged Submit whose Submit was accepted; null "
        "before the first one. Recounted every few minutes (FR-CAT-04)",
    )


class DifficultyTotal(BaseModel):
    difficulty: str
    total: int = Field(description="Published problems of the level, whatever the filters")


class ProblemPage(BaseModel):
    items: list[ProblemListItem]
    page: int
    per_page: int
    total: int = Field(description="Problems that match the filters")
    progress: list[DifficultyTotal] = Field(
        description="Per level, in the order of the levels; solved counts arrive in phase 2"
    )


class PipelineStage(BaseModel):
    key: str = Field(examples=["sim"])
    type: str = Field(examples=["sim"])


class PipelineInfo(BaseModel):
    """Stages of Run and Submit, in order, to draw the pipeline before the first check."""

    run: list[PipelineStage]
    submit: list[PipelineStage]


class ProblemVersionDetail(BaseModel):
    """A version of a problem: its data never changes once published."""

    slug: str
    number: int
    version: int
    current_version: int = Field(description="The version that new submissions are checked on")
    title: str
    difficulty: str
    tags: list[str]
    language: str = Field(examples=["systemverilog"])
    resource_class: str = Field(examples=["light"], description="heavy: not for guests")
    statement_md: str
    template: str
    top: str = Field(description="Name of the module the solution defines")
    interface: Interface
    pipeline: PipelineInfo
    tests: dict[str, int] = Field(
        description="Number of tests per group, e.g. public and hidden", examples=[{"public": 4}]
    )
    changelog: str | None = Field(description="What changed since the previous version")
    published_at: datetime


class ProblemDetail(ProblemVersionDetail):
    """The current version of a problem and its statistics, which change between versions."""

    acceptance: float | None = Field(
        ge=0,
        le=1,
        examples=[0.41],
        description="As in the catalogue: the share of the authors with a judged Submit whose "
        "Submit was accepted; null before the first one (FR-CAT-04)",
    )
