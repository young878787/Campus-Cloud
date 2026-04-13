"""
Models 模組

此模組包含所有資料庫模型定義（DB tables + enums）。
API schemas 已移至 app.schemas 模組。
"""

from sqlmodel import SQLModel

from .ai_api_credential import AIAPICredential
from .ai_api_rate_limit import AIAPIRateLimit
from .ai_api_request import AIAPIRequest, AIAPIRequestStatus
from .ai_api_usage import AIAPIUsage
from .base import get_datetime_utc
from .resource import Resource
from .user import User, UserBase, UserRole
from .vm_migration_job import VMMigrationJob, VMMigrationJobStatus
from .vm_request import VMMigrationStatus, VMRequest, VMRequestStatus
from .audit_log import AuditAction, AuditLog
from .spec_change_request import (
    SpecChangeRequest,
    SpecChangeRequestStatus,
    SpecChangeType,
)
from .group import Group
from .group_member import GroupMember
from .proxmox_config import ProxmoxConfig
from .proxmox_node import ProxmoxNode
from .proxmox_storage import ProxmoxStorage
from .firewall_layout import FirewallLayout
from .nat_rule import NatRule
from .gateway_config import GatewayConfig
from .reverse_proxy_rule import ReverseProxyRule
from .batch_provision import (
    BatchProvisionJob,
    BatchProvisionJobStatus,
    BatchProvisionTask,
    BatchProvisionTaskStatus,
)
from .tunnel_proxy import TunnelProxy

__all__ = [
    # Base
    "SQLModel",
    "get_datetime_utc",
    # User
    "UserBase",
    "User",
    "UserRole",
    # AI API
    "AIAPICredential",
    "AIAPIRequest",
    "AIAPIRequestStatus",
    "AIAPIUsage",
    "AIAPIRateLimit",
    # Resource
    "Resource",
    "VMMigrationJob",
    "VMMigrationJobStatus",
    # VM Request
    "VMMigrationStatus",
    "VMRequest",
    "VMRequestStatus",
    # Audit Log
    "AuditAction",
    "AuditLog",
    # Spec Change Request
    "SpecChangeRequest",
    "SpecChangeRequestStatus",
    "SpecChangeType",
    # Groups
    "Group",
    "GroupMember",
    # Proxmox Config
    "ProxmoxConfig",
    # Proxmox Nodes
    "ProxmoxNode",
    # Proxmox Storages
    "ProxmoxStorage",
    # Firewall Layout
    "FirewallLayout",
    # NAT Rules
    "NatRule",
    # Gateway Config
    "GatewayConfig",
    # Reverse Proxy Rules
    "ReverseProxyRule",
    # Batch Provision
    "BatchProvisionJob",
    "BatchProvisionJobStatus",
    "BatchProvisionTask",
    "BatchProvisionTaskStatus",
    # Tunnel Proxies
    "TunnelProxy",
]
