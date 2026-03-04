from fastapi import APIRouter

from app.api.routes import (
    audit_logs,
    login,
    lxc,
    private,
    resource_details,
    resources,
    spec_change_requests,
    users,
    utils,
    vm,
    vm_requests,
)
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(resources.router)
api_router.include_router(resource_details.router)
api_router.include_router(vm.router)
api_router.include_router(lxc.router)
api_router.include_router(vm_requests.router)
api_router.include_router(spec_change_requests.router)
api_router.include_router(audit_logs.router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
