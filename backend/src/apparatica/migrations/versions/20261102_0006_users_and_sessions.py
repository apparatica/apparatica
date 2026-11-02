"""Phase 2 accounts: users, their identities at login providers, sessions (T2.1a, ADR-0010).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-02 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A trusted extension: the owner of the database may create it.
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("nick", postgresql.CITEXT(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("role", sa.Text(), server_default="user", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("nick ~ '^[a-z0-9_.-]{3,24}$'", name=op.f("ck_users_nick_format")),
        sa.CheckConstraint(
            "role IN ('user', 'author', 'moderator', 'admin')", name=op.f("ck_users_role")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("nick", name=op.f("uq_users_nick")),
    )
    op.create_table(
        "identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_identities_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_identities")),
        sa.UniqueConstraint("provider", "subject", name=op.f("uq_identities_provider_subject")),
    )
    op.create_index(op.f("ix_identities_user_id"), "identities", ["user_id"], unique=False)
    op.create_table(
        "sessions",
        sa.Column("id_hash", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.CheckConstraint("id_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_sessions_id_hash_sha256")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id_hash", name=op.f("pk_sessions")),
    )
    op.create_index(op.f("ix_sessions_expires_at"), "sessions", ["expires_at"], unique=False)
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_expires_at"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_index(op.f("ix_identities_user_id"), table_name="identities")
    op.drop_table("identities")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS citext")
