"""add priority to proxmox_nodes

Revision ID: n5o6p7q8r9s0
Revises: m4n5o6p7q8r9
Create Date: 2026-04-05 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "n5o6p7q8r9s0"
down_revision = "m4n5o6p7q8r9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proxmox_nodes",
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
    )


def downgrade() -> None:
    op.drop_column("proxmox_nodes", "priority")
