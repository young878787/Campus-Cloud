"""add default_node to proxmox_config

Revision ID: m4n5o6p7q8r9
Revises: l3m4n5o6p7q8
Create Date: 2026-04-03 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "m4n5o6p7q8r9"
down_revision = "l3m4n5o6p7q8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proxmox_config",
        sa.Column("default_node", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("proxmox_config", "default_node")
