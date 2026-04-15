"""Add ai_api_usage and ai_template_call_logs tables for AI monitoring.

Revision ID: am01_ai_monitoring
Revises: sk01_ssh_keys
Create Date: 2026-04-15 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "am01_ai_monitoring"
down_revision = "sk01_ssh_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- 建立 ai_api_usage 表 ---
    op.create_table(
        "ai_api_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("credential_id", sa.Uuid(), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("request_type", sa.String(length=50), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_duration_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["credential_id"], ["ai_api_credentials.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_api_usage_user_id"), "ai_api_usage", ["user_id"])
    op.create_index(
        op.f("ix_ai_api_usage_credential_id"), "ai_api_usage", ["credential_id"]
    )
    op.create_index(op.f("ix_ai_api_usage_created_at"), "ai_api_usage", ["created_at"])

    # --- 建立 ai_template_call_logs 表 ---
    op.create_table(
        "ai_template_call_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("call_type", sa.String(length=30), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("preset", sa.String(length=50), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_duration_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ai_template_call_logs_user_id"),
        "ai_template_call_logs",
        ["user_id"],
    )
    op.create_index(
        op.f("ix_ai_template_call_logs_created_at"),
        "ai_template_call_logs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_ai_template_call_logs_created_at"),
        table_name="ai_template_call_logs",
    )
    op.drop_index(
        op.f("ix_ai_template_call_logs_user_id"),
        table_name="ai_template_call_logs",
    )
    op.drop_table("ai_template_call_logs")

    op.drop_index(op.f("ix_ai_api_usage_created_at"), table_name="ai_api_usage")
    op.drop_index(op.f("ix_ai_api_usage_credential_id"), table_name="ai_api_usage")
    op.drop_index(op.f("ix_ai_api_usage_user_id"), table_name="ai_api_usage")
    op.drop_table("ai_api_usage")
