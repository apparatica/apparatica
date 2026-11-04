"""The export of own data (FR-USR-05, GDPR access and portability): the account, its logins, the
legal documents it accepted, every kept submission with its code, and the drafts — one JSON file."""

import uuid
from datetime import datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apparatica.auth.accounts import me
from apparatica.auth.models import Consent, Identity, User
from apparatica.problems.models import Problem, ProblemVersion
from apparatica.submissions.models import Submission
from apparatica.users.models import Draft
from apparatica.users.schemas import (
    AccountExport,
    ExportedConsent,
    ExportedDraft,
    ExportedIdentity,
    ExportedSubmission,
)
from judge.core.stage import SubmissionKind
from judge.core.verdict import SubmissionStatus, VerdictDetail


async def export_account(session: AsyncSession, user: User, now: datetime) -> AccountExport:
    return AccountExport(
        format="apparatica-export/1",
        exported_at=now,
        user=me(user, now),
        identities=await _identities(session, user.id),
        consents=await _consents(session, user.id),
        submissions=await _submissions(session, user.id),
        drafts=await _drafts(session, user.id),
    )


async def _identities(session: AsyncSession, user_id: uuid.UUID) -> list[ExportedIdentity]:
    rows = await session.scalars(
        select(Identity).where(Identity.user_id == user_id).order_by(Identity.created_at)
    )
    return [
        ExportedIdentity(provider=row.provider, email=row.email, created_at=row.created_at)
        for row in rows
    ]


async def _consents(session: AsyncSession, user_id: uuid.UUID) -> list[ExportedConsent]:
    rows = await session.scalars(
        select(Consent).where(Consent.user_id == user_id).order_by(Consent.accepted_at)
    )
    return [
        ExportedConsent(document=row.document, version=row.version, accepted_at=row.accepted_at)
        for row in rows
    ]


async def _submissions(session: AsyncSession, user_id: uuid.UUID) -> list[ExportedSubmission]:
    rows = await session.execute(
        select(Submission, ProblemVersion, Problem.slug)
        .join(ProblemVersion, ProblemVersion.id == Submission.problem_version_id)
        .join(Problem, Problem.id == ProblemVersion.problem_id)
        .where(Submission.user_id == user_id)
        .order_by(Submission.created_at.desc(), Submission.id.desc())
    )
    return [
        ExportedSubmission(
            id=submission.id,
            problem=slug,
            problem_title=version.title,
            version=version.version,
            kind=cast(SubmissionKind, submission.kind),  # ck_submissions_kind
            status=cast(SubmissionStatus, submission.status),  # a submission_status value
            verdict_detail=(
                VerdictDetail.model_validate(submission.verdict_detail)
                if submission.verdict_detail is not None
                else None
            ),
            created_at=submission.created_at,
            finished_at=submission.finished_at,
            code=submission.code,
            seed=str(submission.seed),
            toolchain_profile=submission.toolchain_profile_id,
        )
        for submission, version, slug in rows
    ]


async def _drafts(session: AsyncSession, user_id: uuid.UUID) -> list[ExportedDraft]:
    rows = await session.execute(
        select(Draft, Problem.slug)
        .join(Problem, Problem.id == Draft.problem_id)
        .where(Draft.user_id == user_id)
        .order_by(Draft.updated_at.desc())
    )
    return [
        ExportedDraft(
            problem=slug,
            code=draft.code,
            problem_version=draft.problem_version,
            updated_at=draft.updated_at,
        )
        for draft, slug in rows
    ]
