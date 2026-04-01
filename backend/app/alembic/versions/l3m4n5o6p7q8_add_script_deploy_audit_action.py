"""add script_deploy audit action

Revision ID: l3m4n5o6p7q8
Revises: k2l3m4n5o6p7
Create Date: 2026-03-31 00:00:00.000000

"""

from alembic import op

revision = "l3m4n5o6p7q8"
down_revision = "k2l3m4n5o6p7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'script_deploy'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; downgrade is a no-op
    pass
