"""Schemas of the own account and of public profiles (specs/05 §3, phase 2); the account itself,
`Me`, belongs to auth, which creates it at the first login."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from apparatica.auth.schemas import DisplayName, Me, Nick
from apparatica.submissions.schemas import SubmissionSummary


class MeUpdate(BaseModel):
    """Fields to change; an absent field stays as it is, a null display name is removed."""

    nick: Nick | None = None
    display_name: DisplayName | None = None


class Draft(BaseModel):
    code: str
    problem_version: int = Field(ge=1, description="Version of the problem the code is for")
    updated_at: datetime


class DraftSave(BaseModel):
    code: str = Field(description="Up to limits.solution of GET /config, else CODE_TOO_LARGE")
    problem_version: int = Field(ge=1)


class DifficultyProgress(BaseModel):
    difficulty: str = Field(description="Key of the difficulty levels of GET /config")
    solved: int
    total: int = Field(description="Published problems of the level")


class SolvedProblem(BaseModel):
    slug: str
    number: int
    title: str
    difficulty: str
    solved_at: datetime = Field(description="First accepted Submit")


class Profile(BaseModel):
    """A public profile (FR-USR-04); places, solutions and activity arrive in phases 3-4."""

    nick: Nick
    display_name: str | None
    avatar_url: str | None
    created_at: datetime
    progress: list[DifficultyProgress] = Field(description="In the order of the levels")
    solved: list[SolvedProblem] = Field(description="Newest first")


class ExportedIdentity(BaseModel):
    provider: str = Field(examples=["github", "email"])
    email: str | None
    created_at: datetime


class ExportedSubmission(SubmissionSummary):
    code: str
    seed: str = Field(description="64-bit seed as a decimal string")
    toolchain_profile: str


class ExportedDraft(Draft):
    problem: str = Field(description="Slug of the problem")


class ExportedConsent(BaseModel):
    document: str = Field(examples=["terms", "privacy"])
    version: date = Field(description="The edition of the document (config/legal.yaml)")
    accepted_at: datetime


class AccountExport(BaseModel):
    """Own data as one JSON file (FR-USR-05)."""

    format: Literal["apparatica-export/1"]
    exported_at: datetime
    user: Me
    identities: list[ExportedIdentity]
    consents: list[ExportedConsent] = Field(description="Accepted legal documents (FR-AUTH-06)")
    submissions: list[ExportedSubmission] = Field(description="Newest first, with the code")
    drafts: list[ExportedDraft]
