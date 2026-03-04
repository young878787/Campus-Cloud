import logging

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, SessionDep, VmInfoDep
from app.core.config import settings
from app.core.proxmox import basic_blocking_task_status, get_proxmox_api
from app.crud import audit_log as audit_log_crud
from app.crud import resource as resource_crud
from app.models import VMCreateResponse, VMCreateSchema, VMTemplateSchema, VNCInfoSchema

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vm", tags=["vm"])


@router.get("/{vmid}/console", response_model=VNCInfoSchema)
def get_vm_console(vmid: int, vm_info: VmInfoDep):
    """Get VNC console access for a VM (requires ownership or admin)."""
    try:
        proxmox = get_proxmox_api()
        if vm_info["type"] != "qemu":
            raise HTTPException(
                status_code=400, detail=f"Resource {vmid} is not a QEMU VM"
            )

        node = vm_info["node"]
        console_data = proxmox.nodes(node).qemu(vmid).vncproxy.post(websocket=1)
        vnc_ticket = console_data["ticket"]

        ws_url = f"/ws/vnc/{vmid}/"

        logger.info(f"Console URL and ticket generated for VM {vmid}")

        return {
            "vmid": vmid,
            "ws_url": ws_url,
            "ticket": vnc_ticket,
            "message": "Connect to this WebSocket URL to access the VM console",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get console for VM {vmid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create", response_model=VMCreateResponse)
def create_vm(
    vm_data: VMCreateSchema,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Create a new VM from a cloud-init template."""
    try:
        proxmox = get_proxmox_api()
        # Get next available VMID
        new_vmid = proxmox.cluster.nextid.get()

        # Clone the template
        clone_config = {
            "newid": new_vmid,
            "name": vm_data.hostname,
            "full": 1,  # Full clone
            "storage": settings.PROXMOX_DATA_STORAGE,
            "pool": "CampusCloud",
        }

        # Start the clone task
        logger.info(f"Starting clone task for template {vm_data.template_id}")
        result = (
            proxmox.nodes("pve").qemu(vm_data.template_id).clone.post(**clone_config)
        )

        # Wait for clone task to complete
        basic_blocking_task_status("pve", result)

        # Update VM configuration (cores, memory, cloud-init, etc.)
        config_updates = {
            "cores": vm_data.cores,
            "memory": vm_data.memory,
            "ciuser": vm_data.username,
            "cipassword": vm_data.password,
            "sshkeys": "",
            "ciupgrade": 0,
        }

        proxmox.nodes("pve").qemu(new_vmid).config.put(**config_updates)

        # Resize disk if requested
        if vm_data.disk_size:
            # Update the disk size
            proxmox.nodes("pve").qemu(new_vmid).resize.put(
                disk="scsi0", size=vm_data.disk_size
            )

        # Start the VM if requested
        if vm_data.start:
            proxmox.nodes("pve").qemu(new_vmid).status.start.post()

        # Create resource record in database
        resource_crud.create_resource(
            session=session,
            vmid=new_vmid,
            user_id=current_user.id,
            environment_type=vm_data.environment_type,
            os_info=vm_data.os_info,
            expiry_date=vm_data.expiry_date,
            template_id=vm_data.template_id,
        )

        # Record audit log
        audit_log_crud.create_audit_log(
            session=session,
            user_id=current_user.id,
            vmid=new_vmid,
            action="vm_create",
            details=f"Created VM '{vm_data.hostname}' from template {vm_data.template_id}: {vm_data.cores} cores, {vm_data.memory}MB RAM, {vm_data.disk_size or 'default'} disk",
        )

        logger.info(f"Created VM {new_vmid} from template {vm_data.template_id}")

        return {
            "vmid": new_vmid,
            "upid": result,
            "message": f"VM {vm_data.hostname} created successfully with VMID {new_vmid}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create VM: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates", response_model=list[VMTemplateSchema])
def get_vm_templates(current_user: CurrentUser):
    """Get available VM templates (VMs marked as templates). Requires authentication."""
    try:
        proxmox = get_proxmox_api()
        all_vms = proxmox.cluster.resources.get(type="vm")
        templates = []
        for vm in all_vms:
            if vm.get("template") == 1:
                templates.append(
                    {
                        "vmid": vm["vmid"],
                        "name": vm["name"],
                        "node": vm["node"],
                    }
                )
        logger.info(f"Found {len(templates)} VM templates")
        return templates
    except Exception as e:
        logger.error(f"Failed to get VM templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))
