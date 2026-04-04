import logging
import uuid
from collections.abc import Iterable

from sqlmodel import Session

from app.core.proxmox import get_proxmox_settings
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
from app.services import audit_service, firewall_service, proxmox_service

logger = logging.getLogger(__name__)


def _to_punycode_hostname(hostname: str) -> str:
    """將 Unicode hostname 轉換為 Punycode（ACE 格式）傳給 PVE。"""
    if not isinstance(hostname, str):
        logger.error(
            "Expected str for hostname, got %s: %r", type(hostname).__name__, hostname
        )
        raise TypeError(f"hostname must be str, got {type(hostname).__name__!r}: {hostname!r}")
    result_labels = []
    for label in hostname.split("."):
        try:
            label.encode("ascii")
            result_labels.append(label)  # 純 ASCII，無需轉換
        except UnicodeEncodeError:
            # 使用 punycode codec 編碼非 ASCII 字元
            try:
                ace = "xn--" + label.encode("punycode").decode("ascii")
                result_labels.append(ace)
            except Exception as e:
                raise ValueError(f"Cannot encode hostname label '{label}' to Punycode: {e}") from e
    return ".".join(result_labels)


def _cleanup_failed_resource(node: str, vmid: int, resource_type: str) -> None:
    """Best-effort cleanup for a partially provisioned resource."""
    try:
        try:
            status = proxmox_service.get_status(node, vmid, resource_type)
            if status.get("status") == "running":
                proxmox_service.control(node, vmid, resource_type, "stop")
        except Exception:
            logger.warning("Failed to stop %s %s during cleanup", resource_type, vmid)

        delete_params = {"purge": 1}
        if resource_type == "qemu":
            delete_params["destroy-unreferenced-disks"] = 1
        proxmox_service.delete_resource(node, vmid, resource_type, **delete_params)
        logger.info("Cleaned up partially provisioned %s %s", resource_type, vmid)
    except Exception:
        logger.exception(
            "Failed to clean up partially provisioned %s %s", resource_type, vmid
        )


def cleanup_provisioned_resource(vmid: int) -> None:
    """Find and delete a resource created during a failed approval workflow."""
    resource = proxmox_service.find_resource(vmid)
    _cleanup_failed_resource(resource["node"], vmid, resource["type"])


def _get_lxc_target_node() -> str:
    return proxmox_service.pick_target_node()


def _get_vm_target_node(template_id: int) -> str:
    template = proxmox_service.find_vm_template(template_id)
    return template["node"]


def _dedupe_templates(templates: Iterable[dict]) -> list[dict]:
    unique: dict[str, dict] = {}
    for template in templates:
        volid = template.get("volid")
        if volid:
            unique[volid] = template
    return list(unique.values())


def create_lxc(
    *, session: Session, lxc_data: LXCCreateRequest, user_id: uuid.UUID
) -> LXCCreateResponse:
    vmid = proxmox_service.next_vmid()
    target_node = _get_lxc_target_node()
    target_storage = proxmox_service.resolve_target_storage(
        target_node,
        lxc_data.storage,
        required_content="rootdir",
    )
    created = False
    try:
        config = {
            "vmid": vmid,
            "hostname": _to_punycode_hostname(lxc_data.hostname),
            "ostemplate": lxc_data.ostemplate,
            "cores": lxc_data.cores,
            "memory": lxc_data.memory,
            "swap": 512,
            "rootfs": f"{target_storage}:{lxc_data.rootfs_size}",
            "password": lxc_data.password,
            "net0": "name=eth0,bridge=vmbr0,ip=dhcp,firewall=1",
            "unprivileged": int(lxc_data.unprivileged),
            "start": int(lxc_data.start),
            "pool": get_proxmox_settings().pool_name,
        }

        result = proxmox_service.create_lxc(target_node, **config)
        created = True

        firewall_service.setup_default_rules(target_node, vmid, "lxc")

        resource_repo.create_resource(
            session=session,
            vmid=vmid,
            user_id=user_id,
            environment_type=lxc_data.environment_type,
            os_info=lxc_data.os_info,
            expiry_date=lxc_data.expiry_date,
            commit=False,
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
            commit=False,
        )
        session.commit()

        logger.info(f"Created LXC container {vmid}: {lxc_data.hostname}")
        return LXCCreateResponse(
            vmid=vmid,
            upid=result,
            message=f"Container {lxc_data.hostname} created successfully with VMID {vmid}",
        )
    except Exception as e:
        session.rollback()
        if created:
            _cleanup_failed_resource(target_node, vmid, "lxc")
        logger.error(f"Failed to create LXC container: {e}")
        raise ProxmoxError(f"Failed to create LXC container: {e}")


def create_vm(
    *, session: Session, vm_data: VMCreateRequest, user_id: uuid.UUID
) -> VMCreateResponse:
    new_vmid = proxmox_service.next_vmid()
    target_node = _get_vm_target_node(vm_data.template_id)
    target_storage = proxmox_service.resolve_target_storage(
        target_node,
        vm_data.storage,
        required_content="images",
    )
    created = False
    try:
        clone_config = {
            "newid": new_vmid,
            "name": _to_punycode_hostname(vm_data.hostname),
            "full": 1,
            "storage": target_storage,
            "pool": get_proxmox_settings().pool_name,
        }

        result = proxmox_service.clone_vm(target_node, vm_data.template_id, **clone_config)
        created = True

        config_updates = {
            "cores": vm_data.cores,
            "memory": vm_data.memory,
            "ciuser": vm_data.username,
            "cipassword": vm_data.password,
            "sshkeys": "",
            "ciupgrade": 0,
        }
        proxmox_service.update_config(target_node, new_vmid, "qemu", **config_updates)

        if vm_data.disk_size:
            proxmox_service.resize_disk(
                target_node, new_vmid, "qemu", "scsi0", f"{vm_data.disk_size}G"
            )

        firewall_service.setup_default_rules(target_node, new_vmid, "qemu")

        if vm_data.start:
            proxmox_service.control(target_node, new_vmid, "qemu", "start")

        resource_repo.create_resource(
            session=session,
            vmid=new_vmid,
            user_id=user_id,
            environment_type=vm_data.environment_type,
            os_info=vm_data.os_info,
            expiry_date=vm_data.expiry_date,
            template_id=vm_data.template_id,
            commit=False,
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
            commit=False,
        )
        session.commit()

        logger.info(f"Created VM {new_vmid} from template {vm_data.template_id}")
        return VMCreateResponse(
            vmid=new_vmid,
            upid=result,
            message=f"VM {vm_data.hostname} created successfully with VMID {new_vmid}",
        )
    except Exception as e:
        session.rollback()
        if created:
            _cleanup_failed_resource(target_node, new_vmid, "qemu")
        logger.error(f"Failed to create VM: {e}")
        raise ProxmoxError(f"Failed to create VM: {e}")


def provision_from_request(*, session: Session, db_request) -> int:
    """Provision a VM or LXC based on an approved request. Returns VMID."""
    new_vmid = proxmox_service.next_vmid()
    plain_password = decrypt_value(db_request.password)
    target_node = (
        _get_lxc_target_node()
        if db_request.resource_type == "lxc"
        else _get_vm_target_node(db_request.template_id)
    )
    target_storage = proxmox_service.resolve_target_storage(
        target_node,
        db_request.storage,
        required_content=(
            "rootdir" if db_request.resource_type == "lxc" else "images"
        ),
    )
    resource_type = "lxc" if db_request.resource_type == "lxc" else "qemu"
    created = False

    try:
        if db_request.resource_type == "lxc":
            config = {
                "vmid": new_vmid,
                "hostname": _to_punycode_hostname(db_request.hostname),
                "ostemplate": db_request.ostemplate,
                "cores": db_request.cores,
                "memory": db_request.memory,
                "swap": 512,
                "rootfs": f"{target_storage}:{db_request.rootfs_size or 8}",
                "password": plain_password,
                "net0": "name=eth0,bridge=vmbr0,ip=dhcp,firewall=1",
                "unprivileged": int(db_request.unprivileged),
                "start": 1,
                "pool": get_proxmox_settings().pool_name,
            }
            proxmox_service.create_lxc(target_node, **config)
            created = True

            firewall_service.setup_default_rules(target_node, new_vmid, "lxc")

            resource_repo.create_resource(
                session=session,
                vmid=new_vmid,
                user_id=db_request.user_id,
                environment_type=db_request.environment_type,
                os_info=db_request.os_info,
                expiry_date=db_request.expiry_date,
                commit=False,
            )
        else:
            clone_config = {
                "newid": new_vmid,
                "name": _to_punycode_hostname(db_request.hostname),
                "full": 1,
                "storage": target_storage,
                "pool": get_proxmox_settings().pool_name,
            }
            proxmox_service.clone_vm(
                target_node, db_request.template_id, **clone_config
            )
            created = True

            config_updates = {
                "cores": db_request.cores,
                "memory": db_request.memory,
                "ciuser": db_request.username,
                "cipassword": plain_password,
                "sshkeys": "",
                "ciupgrade": 0,
            }
            proxmox_service.update_config(
                target_node, new_vmid, "qemu", **config_updates
            )

            if db_request.disk_size:
                proxmox_service.resize_disk(
                    target_node, new_vmid, "qemu", "scsi0", f"{db_request.disk_size}G"
                )

            firewall_service.setup_default_rules(target_node, new_vmid, "qemu")
            proxmox_service.control(target_node, new_vmid, "qemu", "start")

            resource_repo.create_resource(
                session=session,
                vmid=new_vmid,
                user_id=db_request.user_id,
                environment_type=db_request.environment_type,
                os_info=db_request.os_info,
                expiry_date=db_request.expiry_date,
                template_id=db_request.template_id,
                commit=False,
            )
    except Exception:
        session.rollback()
        if created:
            _cleanup_failed_resource(target_node, new_vmid, resource_type)
        raise

    logger.info(f"Provisioned {db_request.resource_type} with VMID {new_vmid}")
    return new_vmid


def get_lxc_templates() -> list[TemplateSchema]:
    templates: list[dict] = []
    for node in proxmox_service.get_available_nodes():
        node_name = node.get("node") or node.get("name")
        if not node_name:
            continue
        try:
            templates.extend(proxmox_service.get_lxc_templates(node_name))
        except Exception:
            logger.warning("Failed to load LXC templates from node %s", node_name)

    templates = _dedupe_templates(templates)
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
