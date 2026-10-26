"""Artifacts: when the ingestor deleted the file of an expired artifact (T1.4b, specs/07 §4.4).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-26 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("artifacts", sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_artifacts_expires_at_unpurged",
        "artifacts",
        ["expires_at"],
        unique=False,
        postgresql_where=sa.text("expires_at IS NOT NULL AND purged_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_artifacts_expires_at_unpurged",
        table_name="artifacts",
        postgresql_where=sa.text("expires_at IS NOT NULL AND purged_at IS NULL"),
    )
    op.drop_column("artifacts", "purged_at")
