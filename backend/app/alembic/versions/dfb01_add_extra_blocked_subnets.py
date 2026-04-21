"""add extra_blocked_subnets to subnet_config

Revision ID: dfb01_extra_block
Revises: svct01_resource_service_template
Create Date: 2026-04-19 21:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "dfb01_extra_block"
down_revision = "svct01_resource_service_template"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subnet_config",
        sa.Column("extra_blocked_subnets", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subnet_config", "extra_blocked_subnets")
