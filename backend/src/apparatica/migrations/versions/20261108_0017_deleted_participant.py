"""«Удалённый участник»: the author of the public solutions of deleted accounts (T3.4a, ОВ-12).

The ingestor moves public solutions and their entries of leaderboards to this one row when it
deletes an account, so the user holds many entries of a leaderboard: their uniqueness no longer
covers it.

The downgrade deletes what passed to it, as the deletion of an account did before; the places
close up at the next count of each leaderboard.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-08 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DELETED_USER_ID = "00000000-0000-0000-0000-000000000001"
KEY = ["problem_id", "leaderboard_epoch", "toolchain_profile_id", "formula_version"]


def upgrade() -> None:
    op.execute(f"INSERT INTO users (id, nick) VALUES ('{DELETED_USER_ID}', 'deleted-participant')")
    op.drop_constraint("uq_leaderboard_entries_user", "leaderboard_entries", type_="unique")
    op.create_index(
        "uq_leaderboard_entries_user",
        "leaderboard_entries",
        [*KEY, "user_id"],
        unique=True,
        postgresql_where=sa.text(f"user_id <> '{DELETED_USER_ID}'"),
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM leaderboard_entries WHERE user_id = '{DELETED_USER_ID}'")
    op.drop_index("uq_leaderboard_entries_user", table_name="leaderboard_entries")
    op.create_unique_constraint(
        "uq_leaderboard_entries_user", "leaderboard_entries", [*KEY, "user_id"]
    )
    op.execute(f"DELETE FROM submissions WHERE user_id = '{DELETED_USER_ID}'")
    op.execute(f"DELETE FROM users WHERE id = '{DELETED_USER_ID}'")
