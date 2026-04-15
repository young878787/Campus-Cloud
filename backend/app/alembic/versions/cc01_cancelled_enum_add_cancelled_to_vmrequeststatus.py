"""add cancelled to vmrequeststatus

Revision ID: cc01_cancelled_enum
Revises: f6a7b8c9d0e1
Create Date: 2026-04-13 00:00:00.000000

"""

from alembic import op

revision = "cc01_cancelled_enum"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None

_ENUM_NAME = "vmrequeststatus"


def upgrade() -> None:
    op.execute(
        f"ALTER TYPE {_ENUM_NAME} ADD VALUE IF NOT EXISTS 'cancelled' AFTER 'rejected'"
    )


def downgrade() -> None:
    # PostgreSQL cannot remove enum values; map back to rejected.
    op.execute("UPDATE vm_requests SET status = 'rejected' WHERE status = 'cancelled'")
