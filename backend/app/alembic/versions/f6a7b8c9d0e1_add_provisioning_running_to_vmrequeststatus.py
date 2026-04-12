"""add provisioning and running to vmrequeststatus

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-12 00:00:00.000000

"""

from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None

# The PostgreSQL enum type name matches the lowercase class name.
_ENUM_NAME = "vmrequeststatus"


def upgrade() -> None:
    op.execute(f"ALTER TYPE {_ENUM_NAME} ADD VALUE IF NOT EXISTS 'provisioning' AFTER 'approved'")
    op.execute(f"ALTER TYPE {_ENUM_NAME} ADD VALUE IF NOT EXISTS 'running' AFTER 'provisioning'")


def downgrade() -> None:
    # PostgreSQL cannot remove enum values; convert rows back to 'approved'.
    op.execute(
        "UPDATE vm_requests SET status = 'approved' "
        "WHERE status IN ('provisioning', 'running')"
    )
