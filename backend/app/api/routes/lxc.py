import logging

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, LxcInfoDep, SessionDep
from app.core.config import settings
from app.core.proxmox import basic_blocking_task_status, get_proxmox_api
from app.crud import audit_log as audit_log_crud
from app.crud import resource as resource_crud
from app.models import (
    LXCCreateResponse,
    LXCCreateSchema,
    TemplateSchema,
    TerminalInfoSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lxc", tags=["lxc"])


@router.get("/{vmid}/terminal", response_model=TerminalInfoSchema)
def get_lxc_terminal(vmid: int, container_info: LxcInfoDep):
    """Get terminal access for an LXC container (requires ownership or admin)."""
    try:
        proxmox = get_proxmox_api()
        node = container_info["node"]
        console_data = proxmox.nodes(node).lxc(vmid).termproxy.post()
        terminal_ticket = console_data["ticket"]

        ws_url = f"/ws/terminal/{vmid}/"

        logger.info(f"Terminal URL and ticket generated for LXC {vmid}")

        return {
            "vmid": vmid,
            "ws_url": ws_url,
            "ticket": terminal_ticket,
            "message": "Connect to this WebSocket URL to access the LXC terminal",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get terminal for LXC {vmid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates", response_model=list[TemplateSchema])
def get_templates(current_user: CurrentUser):
    """Get available OS templates for LXC containers. Requires authentication."""
    try:
        proxmox = get_proxmox_api()
        templates = (
            proxmox.nodes("pve").storage(settings.PROXMOX_ISO_STORAGE).content.get()
        )
        lxc_templates = []
        for t in templates:
            if t.get("content") == "vztmpl":
                lxc_templates.append(
                    {
                        "volid": t["volid"],
                        "format": t.get("format", ""),
                        "size": t.get("size", 0),
                    }
                )
        logger.info(f"Found {len(lxc_templates)} LXC templates")
        return lxc_templates
    except Exception as e:
        logger.error(f"Failed to get templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create", response_model=LXCCreateResponse)
def create_lxc(
    lxc_data: LXCCreateSchema,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Create a new LXC container."""
    try:
        proxmox = get_proxmox_api()
        # Get next available VMID
        vmid = proxmox.cluster.nextid.get()

        # Prepare container configuration
        config = {
            "vmid": vmid,
            "hostname": lxc_data.hostname,
            "ostemplate": lxc_data.ostemplate,
            "cores": lxc_data.cores,
            "memory": lxc_data.memory,
            "swap": 512,
            "rootfs": f"{settings.PROXMOX_DATA_STORAGE}:{lxc_data.rootfs_size}",
            "password": lxc_data.password,
            "net0": "name=eth0,bridge=vmbr0,ip=dhcp,firewall=0",
            "unprivileged": 1,
            "start": 1,
            "pool": "CampusCloud",
        }

        # Create the container
        result = proxmox.nodes("pve").lxc.create(**config)

        # Wait for clone task to complete
        basic_blocking_task_status("pve", result)

        # Create resource record in database
        resource_crud.create_resource(
            session=session,
            vmid=vmid,
            user_id=current_user.id,
            environment_type=lxc_data.environment_type,
            os_info=lxc_data.os_info,
            expiry_date=lxc_data.expiry_date,
            template_id=None,
        )

        # Record audit log
        audit_log_crud.create_audit_log(
            session=session,
            user_id=current_user.id,
            vmid=vmid,
            action="lxc_create",
            details=f"Created LXC container '{lxc_data.hostname}': {lxc_data.cores} cores, {lxc_data.memory}MB RAM, {lxc_data.rootfs_size}GB disk",
        )

        logger.info(f"Created LXC container {vmid}: {lxc_data.hostname}")

        return {
            "vmid": vmid,
            "upid": result,
            "message": f"Container {lxc_data.hostname} created successfully with VMID {vmid}",
        }
    except Exception as e:
        logger.error(f"Failed to create LXC container: {e}")
        raise HTTPException(status_code=500, detail=str(e))
