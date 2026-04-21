"""Add service_template_slug and script_path to vm_requests.

Revision ID: st01_service_template
Revises: ip02_drop_pve_ip
Create Date: 2026-05-01 00:00:00.000000

"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision = "st01_service_template"
down_revision = "ip02_drop_pve_ip"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "vm_requests",
        sa.Column(
            "service_template_slug",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
    )
    op.add_column(
        "vm_requests",
        sa.Column(
            "service_template_script_path",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column("vm_requests", "service_template_script_path")
    op.drop_column("vm_requests", "service_template_slug")
