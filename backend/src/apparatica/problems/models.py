"""Tables of problems, their immutable versions, tags and reference solutions (specs/04 §4)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from apparatica.core.db import Base, created_at, uuid_pk


class Tag(Base):
    __tablename__ = "tags"

    slug: Mapped[str] = mapped_column(primary_key=True)
    title: Mapped[str]
    sort: Mapped[int] = mapped_column(server_default="0")


class Problem(Base):
    __tablename__ = "problems"
    __table_args__ = (
        CheckConstraint("number > 0", name="number_positive"),
        # The current version is a version of this problem; the constraint is added after
        # problem_versions exists (the tables refer to each other).
        ForeignKeyConstraint(
            ["id", "current_version_id"],
            ["problem_versions.problem_id", "problem_versions.id"],
            name="fk_problems_current_version",
            use_alter=True,
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(unique=True)
    number: Mapped[int] = mapped_column(unique=True)
    current_version_id: Mapped[uuid.UUID | None]
    is_published: Mapped[bool] = mapped_column(server_default="false")
    created_at: Mapped[datetime] = created_at()


class ProblemVersion(Base):
    """Immutable once published (specs/04 §1): re-import with another content_hash is refused."""

    __tablename__ = "problem_versions"
    __table_args__ = (
        UniqueConstraint("problem_id", "version"),
        UniqueConstraint("problem_id", "id"),  # the target of fk_problems_current_version
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint("leaderboard_epoch > 0", name="leaderboard_epoch_positive"),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="content_hash_sha256"),
        Index("ix_problem_versions_tags", "tags", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id"))
    version: Mapped[int]
    content_hash: Mapped[str]
    language: Mapped[str]
    kind: Mapped[str]
    title: Mapped[str]
    difficulty: Mapped[str]  # a key of config/difficulties.yaml
    tags: Mapped[list[str]] = mapped_column(server_default="{}")
    statement_md: Mapped[str]
    template: Mapped[str]
    changelog: Mapped[str | None]
    interface: Mapped[dict[str, Any]]
    manifest: Mapped[dict[str, Any]]  # the whole problem.yaml
    package_uri: Mapped[str]  # object key in the packages bucket
    resource_class: Mapped[str]
    leaderboard_epoch: Mapped[int]
    published_at: Mapped[datetime] = created_at()


class ReferenceSolution(Base):
    __tablename__ = "reference_solutions"

    id: Mapped[uuid.UUID] = uuid_pk()
    problem_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("problem_versions.id"), index=True
    )
    title: Mapped[str]
    code: Mapped[str]
    explanation_md: Mapped[str | None]
    metrics: Mapped[dict[str, Any] | None]  # filled after the reference runs on a profile
