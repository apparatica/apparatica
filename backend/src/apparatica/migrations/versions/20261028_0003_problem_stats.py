"""Problem stats: authors with a judged and with an accepted Submit (T1.12, FR-CAT-04).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-28 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "problem_stats",
        sa.Column("problem_id", sa.Uuid(), nullable=False),
        sa.Column("authors", sa.Integer(), nullable=False),
        sa.Column("accepted_authors", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "accepted_authors <= authors",
            name=op.f("ck_problem_stats_accepted_within_authors"),
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"], ["problems.id"], name=op.f("fk_problem_stats_problem_id_problems")
        ),
        sa.PrimaryKeyConstraint("problem_id", name=op.f("pk_problem_stats")),
    )


def downgrade() -> None:
    op.drop_table("problem_stats")
