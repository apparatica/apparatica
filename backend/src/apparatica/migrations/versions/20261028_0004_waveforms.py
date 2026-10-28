"""Waveforms: trace windows recorded again after their FST expired (T1.17a, FR-WAV-05).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-28 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "waveforms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("stage_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("artifact_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'failed')", name=op.f("ck_waveforms_status_known")
        ),
        sa.CheckConstraint(
            "(status = 'ready') = (artifact_id IS NOT NULL)",
            name=op.f("ck_waveforms_artifact_iff_ready"),
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["artifacts.id"],
            name=op.f("fk_waveforms_artifact_id_artifacts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_waveforms_submission_id_submissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_waveforms")),
    )
    op.create_index(
        op.f("ix_waveforms_submission_id"), "waveforms", ["submission_id"], unique=False
    )
    op.create_index(
        "uq_waveforms_pending",
        "waveforms",
        ["submission_id", "stage_key"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_waveforms_pending",
        table_name="waveforms",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_index(op.f("ix_waveforms_submission_id"), table_name="waveforms")
    op.drop_table("waveforms")
