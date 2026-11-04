"""Submissions of signed-in users, their drafts and their statuses of problems (T2.7a: FR-EDT-02,
FR-USR-03/06, FR-CAT-03).

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-04 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("submissions", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_submissions_user_id_users"), "submissions", "users", ["user_id"], ["id"]
    )
    op.create_index(
        "ix_submissions_user_id_created_at",
        "submissions",
        ["user_id", sa.literal_column("created_at DESC")],
    )
    op.create_table(
        "drafts",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("problem_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("problem_version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("problem_version > 0", name=op.f("ck_drafts_problem_version_positive")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_drafts_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"], ["problems.id"], name=op.f("fk_drafts_problem_id_problems")
        ),
        sa.PrimaryKeyConstraint("user_id", "problem_id", name=op.f("pk_drafts")),
    )
    op.create_table(
        "user_problem_status",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("problem_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("first_solved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_submission_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('attempted', 'solved')", name=op.f("ck_user_problem_status_status")
        ),
        sa.CheckConstraint(
            "(status = 'solved') = (first_solved_at IS NOT NULL)",
            name=op.f("ck_user_problem_status_solved_at_iff_solved"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_problem_status_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"], ["problems.id"], name=op.f("fk_user_problem_status_problem_id_problems")
        ),
        sa.ForeignKeyConstraint(
            ["last_submission_id"],
            ["submissions.id"],
            name=op.f("fk_user_problem_status_last_submission_id_submissions"),
        ),
        sa.PrimaryKeyConstraint("user_id", "problem_id", name=op.f("pk_user_problem_status")),
    )


def downgrade() -> None:
    op.drop_table("user_problem_status")
    op.drop_table("drafts")
    op.drop_index("ix_submissions_user_id_created_at", table_name="submissions")
    op.drop_constraint(op.f("fk_submissions_user_id_users"), "submissions", type_="foreignkey")
    op.drop_column("submissions", "user_id")
