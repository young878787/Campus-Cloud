from fastapi import APIRouter

from app.api.routes import (
    ai_api,
    ai_monitoring,
    ai_proxy,
    ai_pve_advisor,
    ai_pve_log,
    ai_template_recommendation,
    audit_logs,
    batch_provision,
    cloudflare,
    desktop_client,
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
    reverse_proxy,
    rubric,
    script_deploy,
    spec_change_requests,
    tunnel,
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
api_router.include_router(ai_monitoring.router)
api_router.include_router(ai_proxy.router)
api_router.include_router(ai_pve_log.router)
api_router.include_router(ai_pve_advisor.router)
api_router.include_router(ai_template_recommendation.router)
api_router.include_router(spec_change_requests.router)
api_router.include_router(audit_logs.router)
api_router.include_router(groups.router)
api_router.include_router(batch_provision.router)
api_router.include_router(proxmox_config.router)
api_router.include_router(cloudflare.router)
api_router.include_router(firewall.router)
api_router.include_router(reverse_proxy.router)
api_router.include_router(gateway.router)
api_router.include_router(script_deploy.router)
api_router.include_router(rubric.router)
api_router.include_router(tunnel.router)
api_router.include_router(desktop_client.router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
