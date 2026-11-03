"""Tokens of links in letters: login links (T2.2, FR-AUTH-05).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-03 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_tokens",
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("next", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_email_tokens_token_hash_sha256")
        ),
        sa.CheckConstraint("purpose IN ('login')", name=op.f("ck_email_tokens_purpose")),
        sa.PrimaryKeyConstraint("token_hash", name=op.f("pk_email_tokens")),
    )
    op.create_index(
        op.f("ix_email_tokens_expires_at"), "email_tokens", ["expires_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_email_tokens_expires_at"), table_name="email_tokens")
    op.drop_table("email_tokens")
