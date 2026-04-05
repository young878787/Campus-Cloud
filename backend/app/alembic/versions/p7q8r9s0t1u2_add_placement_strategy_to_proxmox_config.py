"""add placement strategy to proxmox_config

Revision ID: p7q8r9s0t1u2
Revises: o6p7q8r9s0t1
Create Date: 2026-04-05 02:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "p7q8r9s0t1u2"
down_revision = "o6p7q8r9s0t1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proxmox_config",
        sa.Column("placement_strategy", sa.String(length=64), nullable=False, server_default="dominant_share_min"),
    )
    op.add_column(
        "proxmox_config",
        sa.Column("cpu_overcommit_ratio", sa.Float(), nullable=False, server_default="2.0"),
    )
    op.add_column(
        "proxmox_config",
        sa.Column("disk_overcommit_ratio", sa.Float(), nullable=False, server_default="1.0"),
    )


def downgrade() -> None:
    op.drop_column("proxmox_config", "disk_overcommit_ratio")
    op.drop_column("proxmox_config", "cpu_overcommit_ratio")
    op.drop_column("proxmox_config", "placement_strategy")
