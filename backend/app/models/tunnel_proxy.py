"""Tunnel proxy registry — one record per VM per forwarded port.

Each row represents an STCP server-side proxy that runs on Gateway VM's frpc,
forwarding traffic from frps to an internal VM's port.  The desktop client
generates matching STCP *visitor* entries so users can reach their VMs via
localhost.
"""

import secrets
import uuid
from datetime import datetime

from sqlmodel import Column, DateTime, Field, SQLModel


class TunnelProxy(SQLModel, table=True):
    __tablename__ = "tunnel_proxies"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    vmid: int = Field(index=True, description="PVE VMID")
    user_id: uuid.UUID = Field(
        foreign_key="user.id", index=True, description="VM owner"
    )

    # Which port on the internal VM this proxy forwards to
    service: str = Field(
        max_length=10, description="ssh or rdp"
    )
    internal_port: int = Field(description="Port on the VM (22, 3389, ...)")

    # STCP secret key — shared between server proxy and visitor
    secret_key: str = Field(
        default_factory=lambda: secrets.token_urlsafe(24),
        max_length=64,
        description="STCP secret key",
    )

    # The proxy name registered with frps (must be globally unique)
    proxy_name: str = Field(
        max_length=100, unique=True,
        description="frp proxy name, e.g. vm-150-ssh",
    )

    # Localhost port assigned to the visitor side
    # Convention: SSH = 60000 + vmid, RDP = 70000 + vmid
    visitor_port: int = Field(
        description="Localhost port on the desktop client side"
    )

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
