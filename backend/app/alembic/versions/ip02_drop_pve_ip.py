"""remove pve_ip from subnet_config

Revision ID: ip02_drop_pve_ip
Revises: ip01_subnet_ip_mgmt
Create Date: 2026-04-16

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "ip02_drop_pve_ip"
down_revision = "ip01_subnet_ip_mgmt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("subnet_config", "pve_ip")


def downgrade() -> None:
    op.add_column(
        "subnet_config",
        sa.Column("pve_ip", sa.String(length=50), nullable=True),
    )
