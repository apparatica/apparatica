"""Toolchain profiles: the version of the waveform viewer of their traces (T1.17b, ADR-0004).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-28 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("toolchain_profiles", sa.Column("waveview", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("toolchain_profiles", "waveview")
