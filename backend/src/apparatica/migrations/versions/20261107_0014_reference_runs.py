"""Phase 3: runs of reference solutions on the default toolchain profile (T3.3: FR-SYN-04).

A run is a Submit without an author linked to its reference solution; the metrics of a reference
are read from its runs, so `reference_solutions.metrics` goes.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-07 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("submissions", sa.Column("reference_solution_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_submissions_reference_solution_id_reference_solutions"),
        "submissions",
        "reference_solutions",
        ["reference_solution_id"],
        ["id"],
    )
    op.create_check_constraint(
        op.f("ck_submissions_reference_run"),
        "submissions",
        "reference_solution_id IS NULL"
        " OR (user_id IS NULL AND guest_id IS NULL AND kind = 'submit')",
    )
    op.create_index(
        "ix_submissions_reference_runs",
        "submissions",
        ["reference_solution_id", "toolchain_profile_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("reference_solution_id IS NOT NULL"),
    )
    op.drop_column("reference_solutions", "metrics")


def downgrade() -> None:
    op.add_column(
        "reference_solutions",
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.drop_index("ix_submissions_reference_runs", table_name="submissions")
    op.drop_constraint(op.f("ck_submissions_reference_run"), "submissions", type_="check")
    op.drop_constraint(
        op.f("fk_submissions_reference_solution_id_reference_solutions"),
        "submissions",
        type_="foreignkey",
    )
    op.drop_column("submissions", "reference_solution_id")
