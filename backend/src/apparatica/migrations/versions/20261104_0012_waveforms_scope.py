"""The whole failed test as a waveform scope, and the cycles a recorded FST covers (T2.12,
FR-WAV-05).

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-04 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PENDING = sa.text("status = 'pending'")


def upgrade() -> None:
    op.add_column(
        "waveforms",
        sa.Column("scope", sa.Text(), server_default="failure_window", nullable=False),
    )
    op.add_column("waveforms", sa.Column("from_cycle", sa.Integer(), nullable=True))
    op.add_column("waveforms", sa.Column("to_cycle", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_waveforms_scope_known"), "waveforms", "scope IN ('failure_window', 'full_test')"
    )
    op.drop_index("uq_waveforms_pending", table_name="waveforms", postgresql_where=PENDING)
    op.create_index(
        "uq_waveforms_pending",
        "waveforms",
        ["submission_id", "stage_key", "scope"],
        unique=True,
        postgresql_where=PENDING,
    )


def downgrade() -> None:
    op.execute("DELETE FROM waveforms WHERE scope = 'full_test'")
    op.drop_index("uq_waveforms_pending", table_name="waveforms", postgresql_where=PENDING)
    op.create_index(
        "uq_waveforms_pending",
        "waveforms",
        ["submission_id", "stage_key"],
        unique=True,
        postgresql_where=PENDING,
    )
    op.drop_constraint(op.f("ck_waveforms_scope_known"), "waveforms", type_="check")
    op.drop_column("waveforms", "to_cycle")
    op.drop_column("waveforms", "from_cycle")
    op.drop_column("waveforms", "scope")
