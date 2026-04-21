"""Add service_template_slug to resources.

Revision ID: svct01_resource_service_template
Revises: sdl01_script_deploy_logs
Create Date: 2026-04-19 10:30:00.000000

"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision = "svct01_resource_service_template"
down_revision = "sdl01_script_deploy_logs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "resources",
        sa.Column(
            "service_template_slug",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column("resources", "service_template_slug")
