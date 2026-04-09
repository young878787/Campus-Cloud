from fastapi import APIRouter

from app.ai.pve_advisor.router import router as ai_pve_advisor_router
from app.ai.template_recommendation.router import router as ai_template_recommendation_router
from app.api.routes import (
    ai_api,
    ai_proxy,
    audit_logs,
    batch_provision,
    firewall,
    gateway,
    groups,
    login,
    lxc,
    migration_jobs,
    private,
    proxmox_config,
    resource_details,
    resources,
    script_deploy,
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
api_router.include_router(migration_jobs.router)
api_router.include_router(ai_api.router)
api_router.include_router(ai_proxy.router)
api_router.include_router(ai_pve_advisor_router)
api_router.include_router(ai_template_recommendation_router)
api_router.include_router(spec_change_requests.router)
api_router.include_router(audit_logs.router)
api_router.include_router(groups.router)
api_router.include_router(batch_provision.router)
api_router.include_router(proxmox_config.router)
api_router.include_router(firewall.router)
api_router.include_router(gateway.router)
api_router.include_router(script_deploy.router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
