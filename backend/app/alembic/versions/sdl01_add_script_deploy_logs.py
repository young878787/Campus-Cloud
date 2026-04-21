"""Add script_deploy_logs table.

Revision ID: sdl01_script_deploy_logs
Revises: st01_service_template
Create Date: 2026-04-17 00:00:00.000000

"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision = "sdl01_script_deploy_logs"
down_revision = "st01_service_template"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "script_deploy_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("vmid", sa.Integer(), nullable=True),
        sa.Column("template_slug", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False),
        sa.Column("template_name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column("script_path", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column("hostname", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("progress", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column("message", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
    )
    op.create_index("ix_script_deploy_logs_task_id", "script_deploy_logs", ["task_id"])
    op.create_index("ix_script_deploy_logs_user_id", "script_deploy_logs", ["user_id"])
    op.create_index("ix_script_deploy_logs_vmid", "script_deploy_logs", ["vmid"])
    op.create_index("ix_script_deploy_logs_template_slug", "script_deploy_logs", ["template_slug"])
    op.create_index("ix_script_deploy_logs_status", "script_deploy_logs", ["status"])
    op.create_index("ix_script_deploy_logs_created_at", "script_deploy_logs", ["created_at"])


def downgrade():
    op.drop_index("ix_script_deploy_logs_created_at", table_name="script_deploy_logs")
    op.drop_index("ix_script_deploy_logs_status", table_name="script_deploy_logs")
    op.drop_index("ix_script_deploy_logs_template_slug", table_name="script_deploy_logs")
    op.drop_index("ix_script_deploy_logs_vmid", table_name="script_deploy_logs")
    op.drop_index("ix_script_deploy_logs_user_id", table_name="script_deploy_logs")
    op.drop_index("ix_script_deploy_logs_task_id", table_name="script_deploy_logs")
    op.drop_table("script_deploy_logs")
