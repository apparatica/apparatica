"""Phase 3: the global leaderboard of users (T3.9: FR-LB-05, ADR-0006).

`user_ratings` holds the points and places, counted again by the ingestor; the daily snapshots of
places give the shift «за неделю».

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-07 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_ratings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("solved_by_difficulty", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reached_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("formula_version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rank > 0", name=op.f("ck_user_ratings_rank_positive")),
        sa.CheckConstraint("points > 0", name=op.f("ck_user_ratings_points_positive")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_ratings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_ratings")),
    )
    op.create_index("ix_user_ratings_rank", "user_ratings", ["rank"])
    op.create_table(
        "user_rating_snapshots",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_rating_snapshots_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("day", "user_id", name=op.f("pk_user_rating_snapshots")),
    )


def downgrade() -> None:
    op.drop_table("user_rating_snapshots")
    op.drop_index("ix_user_ratings_rank", table_name="user_ratings")
    op.drop_table("user_ratings")
