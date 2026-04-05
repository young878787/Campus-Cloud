from app.api.deps.ai_api_key import AIAPIUserDep, get_current_user_by_ai_api_key
from app.api.deps.auth import (
    AdminUser,
    CurrentUser,
    InstructorUser,
    TokenDep,
    get_current_active_superuser,
    get_current_instructor_or_admin,
    get_current_user,
    get_ws_current_user,
    reusable_oauth2,
)
from app.api.deps.database import SessionDep, get_db
from app.api.deps.proxmox import (
    LxcInfoDep,
    ResourceInfoDep,
    VmInfoDep,
    check_firewall_access,
    check_resource_ownership,
    get_lxc_info,
    get_resource_info,
    get_vm_info,
)

__all__ = [
    # Database
    "get_db",
    "SessionDep",
    # Auth
    "reusable_oauth2",
    "TokenDep",
    "get_current_user",
    "CurrentUser",
    "get_current_active_superuser",
    "AdminUser",
    "get_current_instructor_or_admin",
    "InstructorUser",
    "get_ws_current_user",
    # AI API Key Auth
    "get_current_user_by_ai_api_key",
    "AIAPIUserDep",
    # Proxmox (with permission checks built-in)
    "check_resource_ownership",
    "check_firewall_access",
    "get_vm_info",
    "VmInfoDep",
    "get_lxc_info",
    "LxcInfoDep",
    "get_resource_info",
    "ResourceInfoDep",
]
