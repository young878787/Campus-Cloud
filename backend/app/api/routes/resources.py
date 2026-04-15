import logging

from fastapi import APIRouter

from app.api.deps import (
    AdminUser,
    CurrentUser,
    ResourceInfoDep,
    SessionDep,
)
from app.core.security import decrypt_value
from app.exceptions import ProxmoxError
from app.schemas import Message, NodeSchema, ResourcePublic, SSHKeyResponse
from app.services.proxmox import proxmox_service
from app.services.resource import resource_service
from app.repositories import resource as resource_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("/nodes", response_model=list[NodeSchema])
def list_nodes(current_user: AdminUser):
    try:
        return proxmox_service.list_nodes()
    except Exception as e:
        logger.error(f"Failed to get nodes: {e}")
        raise ProxmoxError("Failed to get nodes")


@router.get("/", response_model=list[ResourcePublic])
def list_resources(
    session: SessionDep, current_user: AdminUser, node: str | None = None
):
    return resource_service.list_all(session=session, node=node)


@router.get("/my", response_model=list[ResourcePublic])
def list_my_resources(session: SessionDep, current_user: CurrentUser):
    return resource_service.list_by_user(
        session=session, user_id=current_user.id
    )


@router.get("/{vmid}", response_model=ResourcePublic)
def get_resource(vmid: int, resource_info: ResourceInfoDep, session: SessionDep):
    return resource_service.get_by_vmid(
        session=session, vmid=vmid, resource_info=resource_info
    )


@router.get("/{vmid}/config")
def get_resource_config(vmid: int, resource_info: ResourceInfoDep):
    return resource_service.get_config(vmid=vmid, resource_info=resource_info)


@router.post("/{vmid}/start")
def start_resource(
    vmid: int,
    resource_info: ResourceInfoDep,
    session: SessionDep,
    current_user: CurrentUser,
):
    return resource_service.control(
        session=session,
        vmid=vmid,
        action="start",
        resource_info=resource_info,
        user_id=current_user.id,
    )


@router.post("/{vmid}/stop")
def stop_resource(
    vmid: int,
    resource_info: ResourceInfoDep,
    session: SessionDep,
    current_user: CurrentUser,
):
    return resource_service.control(
        session=session,
        vmid=vmid,
        action="stop",
        resource_info=resource_info,
        user_id=current_user.id,
    )


@router.post("/{vmid}/reboot")
def reboot_resource(
    vmid: int,
    resource_info: ResourceInfoDep,
    session: SessionDep,
    current_user: CurrentUser,
):
    return resource_service.control(
        session=session,
        vmid=vmid,
        action="reboot",
        resource_info=resource_info,
        user_id=current_user.id,
    )


@router.post("/{vmid}/shutdown")
def shutdown_resource(
    vmid: int,
    resource_info: ResourceInfoDep,
    session: SessionDep,
    current_user: CurrentUser,
):
    return resource_service.control(
        session=session,
        vmid=vmid,
        action="shutdown",
        resource_info=resource_info,
        user_id=current_user.id,
    )


@router.post("/{vmid}/reset")
def reset_resource(
    vmid: int,
    resource_info: ResourceInfoDep,
    session: SessionDep,
    current_user: CurrentUser,
):
    return resource_service.control(
        session=session,
        vmid=vmid,
        action="reset",
        resource_info=resource_info,
        user_id=current_user.id,
    )


@router.delete("/{vmid}")
def delete_resource(
    vmid: int,
    session: SessionDep,
    current_user: CurrentUser,
    resource_info: ResourceInfoDep,
    purge: bool = True,
    force: bool = False,
):
    return resource_service.delete(
        session=session,
        vmid=vmid,
        resource_info=resource_info,
        user_id=current_user.id,
        purge=purge,
        force=force,
    )


@router.get("/{vmid}/ssh-key", response_model=SSHKeyResponse)
def get_ssh_key(
    vmid: int,
    session: SessionDep,
    _current_user: CurrentUser,
    _resource_info: ResourceInfoDep,
):
    """取得資源的 SSH 金鑰（包含私鑰，僅限資源擁有者或管理員）"""
    db_resource = resource_repo.get_resource_by_vmid(session=session, vmid=vmid)
    if not db_resource:
        raise ProxmoxError("Resource not found in database")

    private_key: str | None = None
    if db_resource.ssh_private_key_encrypted:
        private_key = decrypt_value(db_resource.ssh_private_key_encrypted)

    return SSHKeyResponse(
        vmid=vmid,
        ssh_public_key=db_resource.ssh_public_key,
        ssh_private_key=private_key,
    )
