import logging
from typing import Annotated

from fastapi import Depends

from app.api.deps.auth import CurrentUser
from app.api.deps.database import SessionDep
from app.exceptions import PermissionDeniedError
from app.repositories import resource as resource_repo
from app.services import proxmox_service

logger = logging.getLogger(__name__)


def check_resource_ownership(
    vmid: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    """
    Check if the current user owns the resource or is a superuser.
    Raises PermissionDeniedError if the user doesn't have permission.
    """
    # Superusers can access all resources
    if current_user.is_superuser:
        return

    # Check if the resource exists in the database
    db_resource = resource_repo.get_resource_by_vmid(session=session, vmid=vmid)

    if not db_resource:
        # Resource not in database - deny access for non-superusers
        logger.warning(
            f"User {current_user.email} attempted to access unregistered resource {vmid}"
        )
        raise PermissionDeniedError(
            "You don't have permission to access this resource"
        )

    # Check if the user owns this resource
    if db_resource.user_id != current_user.id:
        logger.warning(
            f"User {current_user.email} attempted to access resource {vmid} "
            f"owned by user {db_resource.user_id}"
        )
        raise PermissionDeniedError(
            "You don't have permission to access this resource"
        )


def get_vm_info(
    vmid: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict:
    """Get VM info with permission check (requires ownership or admin)."""
    check_resource_ownership(vmid, current_user, session)
    return proxmox_service.find_resource(vmid)


VmInfoDep = Annotated[dict, Depends(get_vm_info)]


def get_lxc_info(
    vmid: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict:
    """Get LXC info with permission check (requires ownership or admin)."""
    check_resource_ownership(vmid, current_user, session)
    return proxmox_service.find_lxc(vmid)


LxcInfoDep = Annotated[dict, Depends(get_lxc_info)]


def get_resource_info(
    vmid: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict:
    """Get resource info with permission check (requires ownership or admin)."""
    check_resource_ownership(vmid, current_user, session)
    return proxmox_service.find_resource(vmid)


ResourceInfoDep = Annotated[dict, Depends(get_resource_info)]
