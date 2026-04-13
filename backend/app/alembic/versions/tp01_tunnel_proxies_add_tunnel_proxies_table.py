"""add tunnel_proxies table

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-04-12 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "tp01_tunnel_proxies"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tunnel_proxies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vmid", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("service", sa.String(length=10), nullable=False),
        sa.Column("internal_port", sa.Integer(), nullable=False),
        sa.Column("secret_key", sa.String(length=64), nullable=False),
        sa.Column("proxy_name", sa.String(length=100), nullable=False),
        sa.Column("visitor_port", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tunnel_proxies_vmid"), "tunnel_proxies", ["vmid"])
    op.create_index(op.f("ix_tunnel_proxies_user_id"), "tunnel_proxies", ["user_id"])
    op.create_index(
        op.f("ix_tunnel_proxies_proxy_name"),
        "tunnel_proxies",
        ["proxy_name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_tunnel_proxies_proxy_name"), table_name="tunnel_proxies")
    op.drop_index(op.f("ix_tunnel_proxies_user_id"), table_name="tunnel_proxies")
    op.drop_index(op.f("ix_tunnel_proxies_vmid"), table_name="tunnel_proxies")
    op.drop_table("tunnel_proxies")
