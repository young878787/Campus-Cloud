"""add batch provision tables

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c1
Create Date: 2026-04-09 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c1"
branch_labels = None
depends_on = None

# SQLAlchemy 將 Python class 名稱小寫作為 PostgreSQL enum type 名稱
batch_provision_job_status_enum = postgresql.ENUM(
    "pending",
    "running",
    "completed",
    "failed",
    name="batchprovisionjobstatus",
    create_type=False,
)

batch_provision_task_status_enum = postgresql.ENUM(
    "pending",
    "running",
    "completed",
    "failed",
    name="batchprovisiontaskstatus",
    create_type=False,
)


def upgrade() -> None:
    batch_provision_job_status_enum.create(op.get_bind(), checkfirst=True)
    batch_provision_task_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "batch_provision_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("initiated_by", sa.Uuid(), nullable=True),
        sa.Column("resource_type", sa.String(length=10), nullable=False),
        sa.Column("hostname_prefix", sa.String(length=63), nullable=False),
        sa.Column("template_params", sa.Text(), nullable=False),
        sa.Column(
            "status",
            batch_provision_job_status_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["group.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["initiated_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_batch_provision_jobs_group_id"),
        "batch_provision_jobs",
        ["group_id"],
    )
    op.create_index(
        op.f("ix_batch_provision_jobs_created_at"),
        "batch_provision_jobs",
        ["created_at"],
    )

    op.create_table(
        "batch_provision_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("member_index", sa.Integer(), nullable=False),
        sa.Column("vmid", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            batch_provision_task_status_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["job_id"], ["batch_provision_jobs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_batch_provision_tasks_job_id"),
        "batch_provision_tasks",
        ["job_id"],
    )

    # 移除建表用的 server_default（與其他 migration 一致）
    op.alter_column("batch_provision_jobs", "status", server_default=None)
    op.alter_column("batch_provision_jobs", "total", server_default=None)
    op.alter_column("batch_provision_jobs", "done", server_default=None)
    op.alter_column("batch_provision_jobs", "failed_count", server_default=None)
    op.alter_column("batch_provision_tasks", "status", server_default=None)


def downgrade() -> None:
    op.drop_index(
        op.f("ix_batch_provision_tasks_job_id"), table_name="batch_provision_tasks"
    )
    op.drop_table("batch_provision_tasks")

    op.drop_index(
        op.f("ix_batch_provision_jobs_created_at"), table_name="batch_provision_jobs"
    )
    op.drop_index(
        op.f("ix_batch_provision_jobs_group_id"), table_name="batch_provision_jobs"
    )
    op.drop_table("batch_provision_jobs")

    batch_provision_task_status_enum.drop(op.get_bind(), checkfirst=True)
    batch_provision_job_status_enum.drop(op.get_bind(), checkfirst=True)
