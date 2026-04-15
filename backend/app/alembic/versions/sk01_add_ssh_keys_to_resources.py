"""add ssh key columns to resources table

Revision ID: sk01_ssh_keys
Revises: mm01_merge_heads
Create Date: 2025-07-15 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "sk01_ssh_keys"
down_revision = "mm01_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "resources",
        sa.Column("ssh_private_key_encrypted", sa.String(), nullable=True),
    )
    op.add_column(
        "resources",
        sa.Column("ssh_public_key", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("resources", "ssh_public_key")
    op.drop_column("resources", "ssh_private_key_encrypted")
