"""
Schemas 模組

API 請求/回應 schemas，按領域分檔：
- common: 通用 schemas（Message, Token, NewPassword 等）
- user: 使用者相關 schemas
- resource: 資源與 Proxmox 相關 schemas
- vm_request: 虛擬機申請 schemas
- spec_change_request: 規格調整 schemas
- audit_log: 審計日誌 schemas
"""

from .ai_api import (
    AIAPICredentialPublic,
    AIAPICredentialsPublic,
    AIAPIRequestCreate,
    AIAPIRequestPublic,
    AIAPIRequestReview,
    AIAPIRequestsPublic,
)
from .audit_log import AuditLogPublic, AuditLogsPublic
from .common import Message, NewPassword, Token, TokenPayload
from .resource import (
    CurrentStatsResponse,
    DirectSpecUpdateRequest,
    LXCCreateRequest,
    LXCCreateResponse,
    NextVMIDSchema,
    NodeSchema,
    ResourcePublic,
    RRDDataPoint,
    RRDDataResponse,
    SnapshotCreateRequest,
    SnapshotInfo,
    SnapshotResponse,
    TemplateSchema,
    TerminalInfoSchema,
    VMCreateRequest,
    VMCreateResponse,
    VMSchema,
    VMTemplateSchema,
    VNCInfoSchema,
)
from .spec_change_request import (
    SpecChangeRequestCreate,
    SpecChangeRequestPublic,
    SpecChangeRequestReview,
    SpecChangeRequestsPublic,
)
from .user import (
    UpdatePassword,
    UserCreate,
    UserPublic,
    UserRegister,
    UsersPublic,
    UserUpdate,
    UserUpdateMe,
)
from .vm_request import (
    VMRequestCreate,
    VMRequestPublic,
    VMRequestReview,
    VMRequestsPublic,
)
from .group import (
    GroupCreate,
    GroupDetailPublic,
    GroupMemberAdd,
    GroupMemberPublic,
    GroupPublic,
    GroupsPublic,
)
from .firewall import (
    ConnectionCreate,
    ConnectionDelete,
    FirewallOptionsPublic,
    FirewallRuleCreate,
    FirewallRulePublic,
    FirewallRuleUpdate,
    LayoutUpdate,
    PortSpec,
    TopologyEdge,
    TopologyNode,
    TopologyResponse,
)
from .proxmox_config import (
    ProxmoxConfigPublic,
    ProxmoxConfigUpdate,
    ProxmoxConnectionTestResult,
)
from .script_deploy import (
    ScriptDeployRequest,
    ScriptDeployResponse,
    ScriptDeployStatus,
)

__all__ = [
    # Common
    "Message",
    "Token",
    "TokenPayload",
    "NewPassword",
    "AIAPIRequestCreate",
    "AIAPIRequestReview",
    "AIAPIRequestPublic",
    "AIAPIRequestsPublic",
    "AIAPICredentialPublic",
    "AIAPICredentialsPublic",
    # User
    "UserCreate",
    "UserRegister",
    "UserUpdate",
    "UserUpdateMe",
    "UpdatePassword",
    "UserPublic",
    "UsersPublic",
    # Resource / Proxmox
    "NodeSchema",
    "VMSchema",
    "VNCInfoSchema",
    "TerminalInfoSchema",
    "TemplateSchema",
    "VMTemplateSchema",
    "NextVMIDSchema",
    "LXCCreateRequest",
    "LXCCreateResponse",
    "ResourcePublic",
    "VMCreateRequest",
    "VMCreateResponse",
    "CurrentStatsResponse",
    "RRDDataPoint",
    "RRDDataResponse",
    "SnapshotInfo",
    "SnapshotCreateRequest",
    "SnapshotResponse",
    "DirectSpecUpdateRequest",
    # VM Request
    "VMRequestCreate",
    "VMRequestReview",
    "VMRequestPublic",
    "VMRequestsPublic",
    # Audit Log
    "AuditLogPublic",
    "AuditLogsPublic",
    # Spec Change Request
    "SpecChangeRequestCreate",
    "SpecChangeRequestReview",
    "SpecChangeRequestPublic",
    "SpecChangeRequestsPublic",
    # Groups
    "GroupCreate",
    "GroupPublic",
    "GroupsPublic",
    "GroupDetailPublic",
    "GroupMemberAdd",
    "GroupMemberPublic",
    # Firewall
    "PortSpec",
    "ConnectionCreate",
    "ConnectionDelete",
    "FirewallRuleCreate",
    "FirewallRuleUpdate",
    "FirewallRulePublic",
    "FirewallOptionsPublic",
    "LayoutUpdate",
    "TopologyNode",
    "TopologyEdge",
    "TopologyResponse",
    # Proxmox Config
    "ProxmoxConfigPublic",
    "ProxmoxConfigUpdate",
    "ProxmoxConnectionTestResult",
    # Script Deploy
    "ScriptDeployRequest",
    "ScriptDeployResponse",
    "ScriptDeployStatus",
]
