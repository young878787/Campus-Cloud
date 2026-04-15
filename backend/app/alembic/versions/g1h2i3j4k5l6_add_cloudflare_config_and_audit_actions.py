"""add cloudflare config table and audit actions

Revision ID: g1h2i3j4k5l6
Revises: f6a7b8c9d0e1
Create Date: 2026-04-12 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op


revision = "g1h2i3j4k5l6"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


NEW_AUDIT_VALUES = [
    "cloudflare_config_update",
    "cloudflare_zone_create",
    "cloudflare_dns_record_create",
    "cloudflare_dns_record_update",
    "cloudflare_dns_record_delete",
]


def upgrade() -> None:
    for value in NEW_AUDIT_VALUES:
        op.execute(f"ALTER TYPE auditaction ADD VALUE IF NOT EXISTS '{value}'")

    op.create_table(
        "cloudflare_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("encrypted_api_token", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("cloudflare_config")
    # PostgreSQL does not support removing enum values; auditaction downgrade is a no-op.