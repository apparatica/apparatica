"""When the account is deleted: 7 days after the user asked (T2.9, FR-USR-05).

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-04 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("delete_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_users_delete_at",
        "users",
        ["delete_at"],
        postgresql_where=sa.text("delete_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_delete_at", table_name="users")
    op.drop_column("users", "delete_at")
