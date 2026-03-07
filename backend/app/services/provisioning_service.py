import logging
import uuid

from sqlmodel import Session

from app.core.config import settings
from app.core.security import decrypt_value
from app.exceptions import ProxmoxError
from app.schemas import (
    LXCCreateRequest,
    LXCCreateResponse,
    TemplateSchema,
    VMCreateRequest,
    VMCreateResponse,
    VMTemplateSchema,
)
from app.repositories import resource as resource_repo
from app.services import audit_service
from app.services import proxmox_service
from app.services.proxmox_service import DEFAULT_NODE

logger = logging.getLogger(__name__)


def create_lxc(
    *, session: Session, lxc_data: LXCCreateRequest, user_id: uuid.UUID
) -> LXCCreateResponse:
    try:
        vmid = proxmox_service.next_vmid()

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

        result = proxmox_service.create_lxc(DEFAULT_NODE, **config)

        resource_repo.create_resource(
            session=session,
            vmid=vmid,
            user_id=user_id,
            environment_type=lxc_data.environment_type,
            os_info=lxc_data.os_info,
            expiry_date=lxc_data.expiry_date,
        )

        audit_service.log_action(
            session=session,
            user_id=user_id,
            vmid=vmid,
            action="lxc_create",
            details=(
                f"Created LXC '{lxc_data.hostname}': "
                f"{lxc_data.cores} cores, {lxc_data.memory}MB RAM, "
                f"{lxc_data.rootfs_size}GB disk"
            ),
        )

        logger.info(f"Created LXC container {vmid}: {lxc_data.hostname}")
        return LXCCreateResponse(
            vmid=vmid,
            upid=result,
            message=f"Container {lxc_data.hostname} created successfully with VMID {vmid}",
        )
    except Exception as e:
        logger.error(f"Failed to create LXC container: {e}")
        raise ProxmoxError(f"Failed to create LXC container: {e}")


def create_vm(
    *, session: Session, vm_data: VMCreateRequest, user_id: uuid.UUID
) -> VMCreateResponse:
    try:
        new_vmid = proxmox_service.next_vmid()

        clone_config = {
            "newid": new_vmid,
            "name": vm_data.hostname,
            "full": 1,
            "storage": settings.PROXMOX_DATA_STORAGE,
            "pool": "CampusCloud",
        }

        result = proxmox_service.clone_vm(
            DEFAULT_NODE, vm_data.template_id, **clone_config
        )

        config_updates = {
            "cores": vm_data.cores,
            "memory": vm_data.memory,
            "ciuser": vm_data.username,
            "cipassword": vm_data.password,
            "sshkeys": "",
            "ciupgrade": 0,
        }
        proxmox_service.update_config(
            DEFAULT_NODE, new_vmid, "qemu", **config_updates
        )

        if vm_data.disk_size:
            proxmox_service.resize_disk(
                DEFAULT_NODE, new_vmid, "qemu", "scsi0", vm_data.disk_size
            )

        if vm_data.start:
            proxmox_service.control(DEFAULT_NODE, new_vmid, "qemu", "start")

        resource_repo.create_resource(
            session=session,
            vmid=new_vmid,
            user_id=user_id,
            environment_type=vm_data.environment_type,
            os_info=vm_data.os_info,
            expiry_date=vm_data.expiry_date,
            template_id=vm_data.template_id,
        )

        audit_service.log_action(
            session=session,
            user_id=user_id,
            vmid=new_vmid,
            action="vm_create",
            details=(
                f"Created VM '{vm_data.hostname}' from template {vm_data.template_id}: "
                f"{vm_data.cores} cores, {vm_data.memory}MB RAM, "
                f"{vm_data.disk_size or 'default'} disk"
            ),
        )

        logger.info(f"Created VM {new_vmid} from template {vm_data.template_id}")
        return VMCreateResponse(
            vmid=new_vmid,
            upid=result,
            message=f"VM {vm_data.hostname} created successfully with VMID {new_vmid}",
        )
    except Exception as e:
        logger.error(f"Failed to create VM: {e}")
        raise ProxmoxError(f"Failed to create VM: {e}")


def provision_from_request(*, session: Session, db_request) -> int:
    """Provision a VM or LXC based on an approved request. Returns VMID."""
    new_vmid = proxmox_service.next_vmid()
    plain_password = decrypt_value(db_request.password)

    if db_request.resource_type == "lxc":
        config = {
            "vmid": new_vmid,
            "hostname": db_request.hostname,
            "ostemplate": db_request.ostemplate,
            "cores": db_request.cores,
            "memory": db_request.memory,
            "swap": 512,
            "rootfs": f"{settings.PROXMOX_DATA_STORAGE}:{db_request.rootfs_size or 8}",
            "password": plain_password,
            "net0": "name=eth0,bridge=vmbr0,ip=dhcp,firewall=0",
            "unprivileged": 1,
            "start": 1,
            "pool": "CampusCloud",
        }
        proxmox_service.create_lxc(DEFAULT_NODE, **config)

        resource_repo.create_resource(
            session=session,
            vmid=new_vmid,
            user_id=db_request.user_id,
            environment_type=db_request.environment_type,
            os_info=db_request.os_info,
            expiry_date=db_request.expiry_date,
        )
    else:
        clone_config = {
            "newid": new_vmid,
            "name": db_request.hostname,
            "full": 1,
            "storage": settings.PROXMOX_DATA_STORAGE,
            "pool": "CampusCloud",
        }
        proxmox_service.clone_vm(
            DEFAULT_NODE, db_request.template_id, **clone_config
        )

        config_updates = {
            "cores": db_request.cores,
            "memory": db_request.memory,
            "ciuser": db_request.username,
            "cipassword": plain_password,
            "sshkeys": "",
            "ciupgrade": 0,
        }
        proxmox_service.update_config(
            DEFAULT_NODE, new_vmid, "qemu", **config_updates
        )

        if db_request.disk_size:
            proxmox_service.resize_disk(
                DEFAULT_NODE, new_vmid, "qemu",
                "scsi0", f"{db_request.disk_size}G"
            )

        proxmox_service.control(DEFAULT_NODE, new_vmid, "qemu", "start")

        resource_repo.create_resource(
            session=session,
            vmid=new_vmid,
            user_id=db_request.user_id,
            environment_type=db_request.environment_type,
            os_info=db_request.os_info,
            expiry_date=db_request.expiry_date,
            template_id=db_request.template_id,
        )

    logger.info(f"Provisioned {db_request.resource_type} with VMID {new_vmid}")
    return new_vmid


def get_lxc_templates() -> list[TemplateSchema]:
    templates = proxmox_service.get_lxc_templates(DEFAULT_NODE)
    return [
        TemplateSchema(
            volid=t["volid"],
            format=t.get("format", ""),
            size=t.get("size", 0),
        )
        for t in templates
        if t.get("content") == "vztmpl"
    ]


def get_vm_templates() -> list[VMTemplateSchema]:
    all_vms = proxmox_service.get_vm_templates()
    return [
        VMTemplateSchema(vmid=vm["vmid"], name=vm["name"], node=vm["node"])
        for vm in all_vms
    ]
