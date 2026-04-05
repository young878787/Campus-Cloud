"""add proxmox_storages table

Revision ID: o6p7q8r9s0t1
Revises: n5o6p7q8r9s0
Create Date: 2026-04-05 01:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "o6p7q8r9s0t1"
down_revision = "n5o6p7q8r9s0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proxmox_storages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("node_name", sa.String(length=255), nullable=False),
        sa.Column("storage", sa.String(length=255), nullable=False),
        sa.Column("storage_type", sa.String(length=50), nullable=True),
        sa.Column("total_gb", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("used_gb", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("avail_gb", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("can_vm", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("can_lxc", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("can_iso", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("can_backup", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("speed_tier", sa.String(length=20), nullable=False, server_default="unknown"),
        sa.Column("user_priority", sa.Integer(), nullable=False, server_default="5"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_name", "storage", name="uq_proxmox_storages_node_name_storage"),
    )


def downgrade() -> None:
    op.drop_table("proxmox_storages")
