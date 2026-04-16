"""Add gpu_mapping_id to vm_requests table.

Revision ID: gp01_gpu_mapping
Revises: am01_ai_monitoring
Create Date: 2026-04-16 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes

revision = "gp01_gpu_mapping"
down_revision = "am01_ai_monitoring"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "vm_requests",
        sa.Column(
            "gpu_mapping_id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column("vm_requests", "gpu_mapping_id")
