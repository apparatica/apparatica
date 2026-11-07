"""Phase 3: minimal moderation (T3.12: FR-ADM-02, FR-ADM-03).

A moderator hides a public solution or a user: `is_hidden` of the submission or the user takes
them out of public pages and leaderboards; each action goes to `moderation_log` with its reason.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-08 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("is_hidden", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column(
        "submissions",
        sa.Column("is_hidden", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_table(
        "moderation_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('hide', 'unhide', 'set_role')", name=op.f("ck_moderation_log_action")
        ),
        sa.CheckConstraint(
            "target_type IN ('user', 'submission')", name=op.f("ck_moderation_log_target_type")
        ),
        sa.CheckConstraint(
            "length(btrim(reason)) > 0", name=op.f("ck_moderation_log_reason_given")
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_moderation_log_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_moderation_log")),
    )
    op.create_index("ix_moderation_log_actor_id", "moderation_log", ["actor_id"])
    op.create_index("ix_moderation_log_target", "moderation_log", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_index("ix_moderation_log_target", table_name="moderation_log")
    op.drop_index("ix_moderation_log_actor_id", table_name="moderation_log")
    op.drop_table("moderation_log")
    op.drop_column("submissions", "is_hidden")
    op.drop_column("users", "is_hidden")
