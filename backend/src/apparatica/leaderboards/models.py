"""Tables of the leaderboards of problems and of the global leaderboard (specs/04 §4, ADR-0006)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apparatica.core.db import Base, uuid_pk

# A leaderboard: entries of one problem compared on one footing (ADR-0006).
KEY_COLUMNS = ("problem_id", "leaderboard_epoch", "toolchain_profile_id", "formula_version")


class LeaderboardEntry(Base):
    """The best accepted Submit of a user in a leaderboard (FR-LB-02). The ingestor writes it and
    recounts the places and groups of the leaderboard (`apparatica.leaderboards.ranking`)."""

    __tablename__ = "leaderboard_entries"
    __table_args__ = (
        UniqueConstraint(*KEY_COLUMNS, "user_id", name="uq_leaderboard_entries_user"),
        CheckConstraint("rank > 0", name="rank_positive"),
        # A follower of a group takes no place (FR-LB-04).
        CheckConstraint(
            "group_leader_entry_id IS NULL OR rank IS NULL", name="follower_has_no_rank"
        ),
        Index("ix_leaderboard_entries_order", *KEY_COLUMNS, "sort_values", "submitted_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id"))
    leaderboard_epoch: Mapped[int]
    toolchain_profile_id: Mapped[str] = mapped_column(ForeignKey("toolchain_profiles.id"))
    formula_version: Mapped[int]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), unique=True
    )
    # The metrics in the order of the formula, negated where larger ranks higher: Postgres
    # compares arrays element by element, so equal arrays share a place.
    sort_values: Mapped[list[Decimal]] = mapped_column(ARRAY(Numeric))
    ast_hash: Mapped[str | None]  # equal hashes form a group led by the earliest entry
    group_leader_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "leaderboard_entries.id",
            ondelete="SET NULL",
            name="fk_leaderboard_entries_group_leader",  # the generated name is too long
        )
    )
    rank: Mapped[int | None]  # of a leader of a group: RANK() by sort_values
    submitted_at: Mapped[datetime]  # of the submission: earlier leads a group and a place
    updated_at: Mapped[datetime]


class UserRating(Base):
    """A user with points in the global leaderboard (FR-LB-05, ADR-0006): counted again from the
    solved problems and the places of problem leaderboards (`apparatica.leaderboards.rating`)."""

    __tablename__ = "user_ratings"
    __table_args__ = (
        CheckConstraint("rank > 0", name="rank_positive"),
        CheckConstraint("points > 0", name="points_positive"),
        Index("ix_user_ratings_rank", "rank"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    points: Mapped[int]
    solved_by_difficulty: Mapped[dict[str, int]] = mapped_column(JSONB)
    # When the user had everything that gives the points now: the latest first solution of a
    # counted problem or Submit that holds a counted place. Equal points: earlier ranks higher.
    reached_at: Mapped[datetime]
    rank: Mapped[int]  # unique: by points, then reached_at, then user_id
    formula_version: Mapped[int]
    updated_at: Mapped[datetime]


class UserRatingSnapshot(Base):
    """The place of a user at the start of a day (UTC), for «за неделю» (FR-LB-05)."""

    __tablename__ = "user_rating_snapshots"

    day: Mapped[date] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    rank: Mapped[int]
