import logging

from fastapi import APIRouter

from app.api.deps import AdminUser, CurrentUser, LxcInfoDep, SessionDep
from app.exceptions import ProxmoxError
from app.schemas import (
    LXCCreateRequest,
    LXCCreateResponse,
    TemplateSchema,
    TerminalInfoSchema,
)
from app.services.proxmox import provisioning_service, proxmox_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lxc", tags=["lxc"])


@router.get("/{vmid}/terminal", response_model=TerminalInfoSchema)
def get_lxc_terminal(vmid: int, container_info: LxcInfoDep):
    """Get terminal access for an LXC container (requires ownership or admin)."""
    try:
        node = container_info["node"]
        console_data = proxmox_service.get_terminal_ticket(node, vmid)

        return {
            "vmid": vmid,
            "ws_url": f"/ws/terminal/{vmid}/",
            "ticket": console_data["ticket"],
            "message": "Connect to this WebSocket URL to access the LXC terminal",
        }
    except ProxmoxError:
        raise
    except Exception as e:
        logger.error(f"Failed to get terminal for LXC {vmid}: {e}")
        raise ProxmoxError("Failed to get LXC terminal")


@router.get("/templates", response_model=list[TemplateSchema])
def get_templates(current_user: CurrentUser):
    return provisioning_service.get_lxc_templates()


@router.post("/create", response_model=LXCCreateResponse)
def create_lxc(
    lxc_data: LXCCreateRequest, session: SessionDep, current_user: AdminUser
):
    return provisioning_service.create_lxc(
        session=session, lxc_data=lxc_data, user_id=current_user.id
    )
