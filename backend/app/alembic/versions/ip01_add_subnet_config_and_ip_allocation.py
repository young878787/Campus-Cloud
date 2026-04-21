"""add subnet_config and ip_allocation tables

Revision ID: ip01_subnet_ip_mgmt
Revises: gp01_gpu_mapping
Create Date: 2026-04-16

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "ip01_subnet_ip_mgmt"
down_revision = "gp01_gpu_mapping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subnet_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cidr", sa.String(length=50), nullable=False),
        sa.Column("gateway", sa.String(length=50), nullable=False),
        sa.Column("bridge_name", sa.String(length=50), nullable=False),
        sa.Column("gateway_vm_ip", sa.String(length=50), nullable=False),
        sa.Column("dns_servers", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "ip_allocation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ip_address", sa.String(length=50), nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("vmid", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ip_allocation_ip_address"),
        "ip_allocation",
        ["ip_address"],
        unique=True,
    )
    op.create_index(
        op.f("ix_ip_allocation_vmid"),
        "ip_allocation",
        ["vmid"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ip_allocation_vmid"), table_name="ip_allocation")
    op.drop_index(op.f("ix_ip_allocation_ip_address"), table_name="ip_allocation")
    op.drop_table("ip_allocation")
    op.drop_table("subnet_config")
