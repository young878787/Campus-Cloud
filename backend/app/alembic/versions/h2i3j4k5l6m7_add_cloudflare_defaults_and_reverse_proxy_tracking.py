"""add cloudflare defaults and reverse proxy tracking

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-04-14 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op


revision = "h2i3j4k5l6m7"
down_revision = "g1h2i3j4k5l6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cloudflare_config",
        sa.Column(
            "default_dns_target_type",
            sa.String(length=16),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "cloudflare_config",
        sa.Column(
            "default_dns_target_value",
            sa.String(length=255),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "reverse_proxy_rule",
        sa.Column("zone_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "reverse_proxy_rule",
        sa.Column("cloudflare_record_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reverse_proxy_rule", "cloudflare_record_id")
    op.drop_column("reverse_proxy_rule", "zone_id")
    op.drop_column("cloudflare_config", "default_dns_target_value")
    op.drop_column("cloudflare_config", "default_dns_target_type")