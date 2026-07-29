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
from .ai_template_call_log import AITemplateCallLog
from .alert_event import AlertEvent, AlertMetric, AlertScope
from .audit_log import AuditAction, AuditLog
from .base import get_datetime_utc
from .batch_provision import (
    BatchProvisionJob,
    BatchProvisionJobStatus,
    BatchProvisionTask,
    BatchProvisionTaskStatus,
)
from .cloudflare_config import CloudflareConfig
from .course import (
    CourseDeployment,
    CourseDifficulty,
    CoursePath,
    CoursePathStatus,
    CourseQuestion,
    CourseQuestionType,
    CourseRoom,
    CourseTask,
    UserCourseProgress,
)
from .deletion_request import DeletionRequest, DeletionRequestStatus
from .execution_profile import ExecutionProfile, ExecutionProfileCommand
from .firewall_layout import FirewallLayout
from .gateway_config import GatewayConfig
from .governance_config import GovernanceConfig
from .group import Group
from .group_member import GroupMember
from .ip_allocation import IpAllocation
from .ldap_config import LdapConfig
from .mining_incident import MiningIncident, MiningIncidentStatus
from .nat_rule import NatRule
from .proxmox_config import (
    ProxmoxConfig,
    ProxmoxConnectionConfig,
    ProxmoxPlacementConfig,
    ProxmoxSchedulerConfig,
)
from .proxmox_node import ProxmoxNode
from .proxmox_storage import ProxmoxStorage
from .resource import Resource
from .resource_network import ResourceNetwork
from .resource_quota import QuotaScope, ResourceQuota
from .reverse_proxy_rule import ReverseProxyRule
from .script_deploy_log import ScriptDeployLog
from .spec_change_request import (
    SpecChangeRequest,
    SpecChangeRequestStatus,
    SpecChangeType,
)
from .subnet_config import SubnetConfig
from .task_record import TaskRecord, TaskRecordStatus
from .teacher_judge_file import TeacherJudgeFile, TeacherJudgeFileStatus
from .teacher_judge_script_artifact import (
    TeacherJudgeScriptArtifact,
    TeacherJudgeScriptLanguage,
    TeacherJudgeScriptSource,
    TeacherJudgeScriptStatus,
)
from .teacher_judge_script_run import (
    TeacherJudgeScriptRun,
    TeacherJudgeScriptRunStatus,
    TeacherJudgeScriptRunTargetScope,
)
from .teaching_class import (
    TeachingClass,
    TeachingClassMachineNode,
    TeachingClassStatus,
    TeachingClassStudent,
    TeachingClassStudentMachine,
    TeachingClassTaskFile,
    TeachingClassWeek,
)
from .tunnel_proxy import TunnelProxy
from .user import User, UserBase, UserRole
from .vm_request import (
    VMProvisioningStatus,
    VMRequest,
    VMRequestProvisioningState,
    VMRequestReviewState,
    VMRequestScheduleState,
    VMRequestStatus,
)
from .vm_template import (
    VMTemplate,
    VMTemplateGroupLink,
    VMTemplateStatus,
    VMTemplateVisibility,
)

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
    "AITemplateCallLog",
    # Resource
    "Resource",
    "ExecutionProfile",
    "ExecutionProfileCommand",
    "ResourceNetwork",
    "ResourceQuota",
    "QuotaScope",
    # VM Request
    "VMProvisioningStatus",
    "VMRequest",
    "VMRequestStatus",
    "VMRequestProvisioningState",
    "VMRequestReviewState",
    "VMRequestScheduleState",
    # Audit Log
    "AuditAction",
    "AuditLog",
    # Governance / Alerts
    "AlertEvent",
    "AlertMetric",
    "AlertScope",
    "GovernanceConfig",
    "MiningIncident",
    "MiningIncidentStatus",
    # LDAP
    "LdapConfig",
    # Spec Change Request
    "SpecChangeRequest",
    "SpecChangeRequestStatus",
    "SpecChangeType",
    # Groups
    "Group",
    "GroupMember",
    # Proxmox Config
    "ProxmoxConfig",
    "ProxmoxConnectionConfig",
    "ProxmoxPlacementConfig",
    "ProxmoxSchedulerConfig",
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
    # Cloudflare Config
    "CloudflareConfig",
    # Reverse Proxy Rules
    "ReverseProxyRule",
    # Batch Provision
    "BatchProvisionJob",
    "BatchProvisionJobStatus",
    "BatchProvisionTask",
    "BatchProvisionTaskStatus",
    # Tunnel Proxies
    "TunnelProxy",
    # Subnet & IP Management
    "SubnetConfig",
    "IpAllocation",
    "ScriptDeployLog",
    "TeacherJudgeFile",
    "TeacherJudgeFileStatus",
    "TeacherJudgeScriptArtifact",
    "TeacherJudgeScriptLanguage",
    "TeacherJudgeScriptRun",
    "TeacherJudgeScriptRunStatus",
    "TeacherJudgeScriptRunTargetScope",
    "TeacherJudgeScriptSource",
    "TeacherJudgeScriptStatus",
    # Deletion Request
    "DeletionRequest",
    "DeletionRequestStatus",
    # VM Template (範本系統 2.0)
    "VMTemplate",
    "VMTemplateGroupLink",
    "VMTemplateStatus",
    "VMTemplateVisibility",
    # Task Record (背景任務)
    "TaskRecord",
    "TaskRecordStatus",
    "TeachingClass",
    "TeachingClassStatus",
    "TeachingClassMachineNode",
    "TeachingClassWeek",
    "TeachingClassTaskFile",
    "TeachingClassStudent",
    "TeachingClassStudentMachine",
    # Course Lab (互動式實作教學)
    "CoursePath",
    "CoursePathStatus",
    "CourseRoom",
    "CourseDifficulty",
    "CourseTask",
    "CourseQuestion",
    "CourseQuestionType",
    "UserCourseProgress",
    "CourseDeployment",
]
