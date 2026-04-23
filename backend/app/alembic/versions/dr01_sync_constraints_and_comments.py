"""sync constraints and comments to match models

- Drop unique constraint (node_name, storage) on proxmox_storages (model no longer requires it)
- Add unique constraint on tunnel_proxies.proxy_name (model declares unique=True)
- Set comment on ai_api_credentials.rate_limit to match model description

Revision ID: dr01_sync_constraints
Revises: d4ffdd95ee6e
Create Date: 2026-04-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "dr01_sync_constraints"
down_revision = "d4ffdd95ee6e"
branch_labels = None
depends_on = None


def upgrade():
    # 1. proxmox_storages: drop legacy unique constraint
    op.drop_constraint(
        "uq_proxmox_storages_node_name_storage",
        "proxmox_storages",
        type_="unique",
    )

    # 2. tunnel_proxies: add unique constraint on proxy_name
    #    (a unique index already exists; constraint keeps autogenerate clean)
    op.create_unique_constraint(
        "uq_tunnel_proxies_proxy_name",
        "tunnel_proxies",
        ["proxy_name"],
    )

    # 3. ai_api_credentials.rate_limit: align comment with model
    op.alter_column(
        "ai_api_credentials",
        "rate_limit",
        existing_type=sa.Integer(),
        existing_nullable=True,
        comment="每分鐘請求限制（1-1000），None 使用預設值 20",
    )


def downgrade():
    op.alter_column(
        "ai_api_credentials",
        "rate_limit",
        existing_type=sa.Integer(),
        existing_nullable=True,
        comment=None,
    )
    op.drop_constraint(
        "uq_tunnel_proxies_proxy_name",
        "tunnel_proxies",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_proxmox_storages_node_name_storage",
        "proxmox_storages",
        ["node_name", "storage"],
    )
