"""The parameter set of a stage instance (T3a.5, ADR-0014, specs/04 §4).

A stage checked at several parameter sets runs as one instance per set: the instance of the
primary set has the stage key and the set `default`, an extra one `<stage key>@<set id>` and the
id of its set. A stage at the primary set only has no set. The values of a set live in the package
of the problem version, not in the row.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-12 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The set an instance key names is the set of the row: none after `@` for the primary set.
PARAM_SET_OF_KEY = "split_part(stage_key, '@', 2) = coalesce(nullif(param_set, 'default'), '')"


def upgrade() -> None:
    op.add_column("stage_results", sa.Column("param_set", sa.Text(), nullable=True))
    op.create_check_constraint("param_set_of_key", "stage_results", PARAM_SET_OF_KEY)


def downgrade() -> None:
    # The instances stay: the API before this revision shows them with no set (T3a.0).
    op.drop_column("stage_results", "param_set")
