"""Phase 3: leaderboards of problems and public solutions (T3.4: FR-LB-01/02/04, ADR-0006).

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-07 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KEY = ["problem_id", "leaderboard_epoch", "toolchain_profile_id", "formula_version"]


def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column("is_public", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_table(
        "leaderboard_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("problem_id", sa.Uuid(), nullable=False),
        sa.Column("leaderboard_epoch", sa.Integer(), nullable=False),
        sa.Column("toolchain_profile_id", sa.Text(), nullable=False),
        sa.Column("formula_version", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("sort_values", postgresql.ARRAY(sa.Numeric()), nullable=False),
        sa.Column("ast_hash", sa.Text(), nullable=True),
        sa.Column("group_leader_entry_id", sa.Uuid(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rank > 0", name=op.f("ck_leaderboard_entries_rank_positive")),
        sa.CheckConstraint(
            "group_leader_entry_id IS NULL OR rank IS NULL",
            name=op.f("ck_leaderboard_entries_follower_has_no_rank"),
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"], ["problems.id"], name=op.f("fk_leaderboard_entries_problem_id_problems")
        ),
        sa.ForeignKeyConstraint(
            ["toolchain_profile_id"],
            ["toolchain_profiles.id"],
            name=op.f("fk_leaderboard_entries_toolchain_profile_id_toolchain_profiles"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_leaderboard_entries_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_leaderboard_entries_submission_id_submissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["group_leader_entry_id"],
            ["leaderboard_entries.id"],
            name="fk_leaderboard_entries_group_leader",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leaderboard_entries")),
        sa.UniqueConstraint(*KEY, "user_id", name="uq_leaderboard_entries_user"),
        sa.UniqueConstraint("submission_id", name=op.f("uq_leaderboard_entries_submission_id")),
    )
    op.create_index(
        "ix_leaderboard_entries_order",
        "leaderboard_entries",
        [*KEY, "sort_values", "submitted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_leaderboard_entries_order", table_name="leaderboard_entries")
    op.drop_table("leaderboard_entries")
    op.drop_column("submissions", "is_public")
