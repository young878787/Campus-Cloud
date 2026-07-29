"""Remove the duplicate profile_key unique constraint.

The execution profile model declares ``profile_key`` as a unique indexed
column.  The initial migration also created a table-level unique constraint,
which duplicated the same PostgreSQL uniqueness enforcement and caused
``alembic check`` to report schema drift.
"""

import sqlalchemy as sa
from alembic import op


revision = "ep02_profile_key_index"
down_revision = "ep01_execution_profiles"
branch_labels = None
depends_on = None

_LEGACY_CONSTRAINT = "execution_profiles_profile_key_key"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("execution_profiles"):
        return
    constraints = inspector.get_unique_constraints("execution_profiles")
    if any(item.get("name") == _LEGACY_CONSTRAINT for item in constraints):
        op.drop_constraint(
            _LEGACY_CONSTRAINT,
            "execution_profiles",
            type_="unique",
        )


def downgrade() -> None:
    # The canonical ep01 schema uses the unique index declared by the model;
    # no duplicate table-level constraint is restored on downgrade.
    return
