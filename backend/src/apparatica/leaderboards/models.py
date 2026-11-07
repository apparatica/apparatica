"""Tables of the leaderboards of problems (specs/04 §4, ADR-0006)."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
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
