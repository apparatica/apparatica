"""Editions of the legal documents users accepted at the first login (T2.5, FR-AUTH-06).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-03 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "consents",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("document", sa.Text(), nullable=False),
        sa.Column("version", sa.Date(), nullable=False),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("document IN ('terms', 'privacy')", name=op.f("ck_consents_document")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_consents_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "document", "version", name=op.f("pk_consents")),
    )


def downgrade() -> None:
    op.drop_table("consents")
