"""獨立反向代理管理 API 路由。"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.deps import AdminUser, CurrentUser, SessionDep, check_firewall_access
from app.core.authorizers import can_bypass_resource_ownership
from app.exceptions import BadRequestError, ProxmoxError
from app.models import AuditAction
from app.repositories import resource as resource_repo
from app.repositories import reverse_proxy as rp_repo
from app.schemas import Message
from app.schemas.firewall import ReverseProxyRulePublic
from app.schemas.reverse_proxy import (
    ReverseProxyRuleCreate,
    ReverseProxyRuleUpdate,
    ReverseProxySetupContext,
    ReverseProxyRuntimeSnapshot,
)
from app.services.network import reverse_proxy_service, traefik_runtime_service
from app.services.user import audit_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reverse-proxy", tags=["reverse-proxy"])


def _get_visible_rules(session: SessionDep, current_user: CurrentUser):
    rules = rp_repo.list_rules(session)
    if can_bypass_resource_ownership(current_user):
        return rules

    own_resources = resource_repo.get_resources_by_user(
        session=session,
        user_id=current_user.id,
    )
    own_vmids = {resource.vmid for resource in own_resources}
    return [rule for rule in rules if rule.vmid in own_vmids]


def _serialize_rule(rule) -> ReverseProxyRulePublic:
    return ReverseProxyRulePublic(
        id=rule.id,
        vmid=rule.vmid,
        vm_ip=rule.vm_ip,
        domain=rule.domain,
        zone_id=rule.zone_id,
        internal_port=rule.internal_port,
        enable_https=rule.enable_https,
        dns_provider=rule.dns_provider,
        created_at=rule.created_at,
    )


def _extract_string_list(payload: Any) -> list[str]:
    if isinstance(payload, list):
        return [str(item) for item in payload if isinstance(item, str)]
    return []


def _filter_runtime_snapshot(
    snapshot: ReverseProxyRuntimeSnapshot,
    session: SessionDep,
    current_user: CurrentUser,
) -> ReverseProxyRuntimeSnapshot:
    if can_bypass_resource_ownership(current_user):
        return snapshot

    visible_rules = _get_visible_rules(session, current_user)
    router_names = {
        reverse_proxy_service.build_runtime_name(rule.vmid, rule.domain)
        for rule in visible_rules
    }
    service_names = {f"{router_name}-svc" for router_name in router_names}

    filtered_http_routers = [
        router
        for router in snapshot.http.routers
        if str(router.get("name", "")) in router_names
    ]
    filtered_http_services = [
        service
        for service in snapshot.http.services
        if str(service.get("name", "")) in service_names
    ]

    referenced_entrypoints: set[str] = set()
    referenced_middlewares: set[str] = set()
    for router in filtered_http_routers:
        referenced_entrypoints.update(
            _extract_string_list(
                router.get("entryPoints") or router.get("entrypoints") or []
            )
        )
        referenced_middlewares.update(
            _extract_string_list(router.get("middlewares") or [])
        )

    filtered_entrypoints = [
        entrypoint
        for entrypoint in snapshot.entrypoints
        if str(entrypoint.get("name", "")) in referenced_entrypoints
    ]
    filtered_http_middlewares = [
        middleware
        for middleware in snapshot.http.middlewares
        if str(middleware.get("name", "")) in referenced_middlewares
    ]

    return ReverseProxyRuntimeSnapshot(
        runtime_error=snapshot.runtime_error,
        version=snapshot.version,
        overview=None,
        entrypoints=filtered_entrypoints,
        http={
            "routers": filtered_http_routers,
            "services": filtered_http_services,
            "middlewares": filtered_http_middlewares,
        },
        tcp={"routers": [], "services": [], "middlewares": []},
        udp={"routers": [], "services": [], "middlewares": []},
    )


@router.get("/runtime", response_model=ReverseProxyRuntimeSnapshot)
def get_runtime_snapshot(session: SessionDep, current_user: CurrentUser):
    try:
        snapshot = traefik_runtime_service.get_runtime_snapshot(session=session)
    except (BadRequestError, ProxmoxError) as exc:
        logger.warning("Unable to fetch Traefik runtime: %s", exc)
        return ReverseProxyRuntimeSnapshot(runtime_error=str(exc))
    except Exception:
        logger.exception("Failed to fetch Traefik runtime snapshot")
        return ReverseProxyRuntimeSnapshot(runtime_error="無法取得 Traefik runtime 狀態")

    return _filter_runtime_snapshot(snapshot, session, current_user)


@router.get("/rules", response_model=list[ReverseProxyRulePublic])
def list_reverse_proxy_rules(session: SessionDep, current_user: CurrentUser):
    return [_serialize_rule(rule) for rule in _get_visible_rules(session, current_user)]


@router.get("/setup-context", response_model=ReverseProxySetupContext)
def get_setup_context(session: SessionDep, _: CurrentUser):
    return reverse_proxy_service.get_reverse_proxy_setup_context(session=session)


@router.post("/rules", response_model=Message)
def create_reverse_proxy_rule(
    body: ReverseProxyRuleCreate,
    session: SessionDep,
    current_user: CurrentUser,
):
    check_firewall_access(vmid=body.vmid, current_user=current_user, session=session)

    vm_ip = reverse_proxy_service.resolve_vmid_ip(vmid=body.vmid, session=session)
    if not vm_ip:
        raise HTTPException(
            status_code=400,
            detail="無法取得 VM IP，請確認 VM 已開機且已取得網路位址",
        )

    try:
        reverse_proxy_service.apply_reverse_proxy_rule(
            session=session,
            vmid=body.vmid,
            vm_ip=vm_ip,
            zone_id=body.zone_id,
            hostname_prefix=body.hostname_prefix,
            internal_port=body.internal_port,
            enable_https=body.enable_https,
        )
        return Message(message="反向代理規則已建立")
    except BadRequestError as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    except ProxmoxError as exc:
        logger.error("Proxmox error creating reverse proxy rule: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception:
        logger.exception("Failed to create reverse proxy rule")
        raise HTTPException(status_code=500, detail="建立反向代理規則失敗")


@router.put("/rules/{rule_id}", response_model=Message)
def update_reverse_proxy_rule(
    rule_id: str,
    body: ReverseProxyRuleUpdate,
    session: SessionDep,
    current_user: CurrentUser,
):
    try:
        rule_uuid = uuid.UUID(rule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="無效的規則 ID")

    existing_rule = rp_repo.get_rule(session, rule_uuid)
    if existing_rule is None:
        raise HTTPException(status_code=404, detail="反向代理規則不存在")

    check_firewall_access(vmid=existing_rule.vmid, current_user=current_user, session=session)
    if body.vmid != existing_rule.vmid:
        check_firewall_access(vmid=body.vmid, current_user=current_user, session=session)

    vm_ip = reverse_proxy_service.resolve_vmid_ip(vmid=body.vmid, session=session)
    if not vm_ip:
        raise HTTPException(
            status_code=400,
            detail="無法取得 VM IP，請確認 VM 已開機且已取得網路位址",
        )

    try:
        reverse_proxy_service.update_reverse_proxy_rule(
            session=session,
            rule_id=rule_id,
            vmid=body.vmid,
            vm_ip=vm_ip,
            zone_id=body.zone_id,
            hostname_prefix=body.hostname_prefix,
            internal_port=body.internal_port,
            enable_https=body.enable_https,
        )
        return Message(message="反向代理規則已更新")
    except BadRequestError as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    except ProxmoxError as exc:
        logger.error("Proxmox error updating reverse proxy rule %s: %s", rule_id, exc)
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception:
        logger.exception("Failed to update reverse proxy rule %s", rule_id)
        raise HTTPException(status_code=500, detail="更新反向代理規則失敗")


@router.delete("/rules/{rule_id}", response_model=Message)
def delete_reverse_proxy_rule(
    rule_id: str,
    session: SessionDep,
    current_user: CurrentUser,
):
    try:
        rule_uuid = uuid.UUID(rule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="無效的規則 ID")

    rule = rp_repo.get_rule(session, rule_uuid)
    if rule is None:
        raise HTTPException(status_code=404, detail="反向代理規則不存在")

    check_firewall_access(vmid=rule.vmid, current_user=current_user, session=session)

    try:
        reverse_proxy_service.remove_reverse_proxy_rule_by_id(
            session=session,
            rule_id=rule_id,
        )
        audit_service.log_action(
            session=session,
            user_id=current_user.id,
            vmid=rule.vmid,
            action=AuditAction.reverse_proxy_rule_delete,
            details=(
                f"Deleted reverse proxy rule {rule_id} "
                f"(vmid={rule.vmid} domain={rule.domain})"
            ),
        )
        return Message(message="反向代理規則已刪除")
    except ProxmoxError as exc:
        logger.error("Proxmox error removing reverse proxy rule %s: %s", rule_id, exc)
        raise HTTPException(status_code=502, detail="Proxmox 操作失敗")
    except Exception:
        logger.exception("Failed to remove reverse proxy rule %s", rule_id)
        raise HTTPException(status_code=500, detail="刪除反向代理規則失敗")


@router.post("/rules/sync", response_model=Message)
def sync_reverse_proxy_rules(session: SessionDep, current_user: AdminUser):
    try:
        reverse_proxy_service.sync_to_gateway(session=session)
        audit_service.log_action(
            session=session,
            user_id=current_user.id,
            action=AuditAction.reverse_proxy_rule_sync,
            details="Manually synced reverse proxy rules to Gateway VM",
        )
        return Message(message="反向代理規則已同步到 Gateway VM")
    except ProxmoxError as exc:
        logger.error("Proxmox error syncing reverse proxy rules: %s", exc)
        raise HTTPException(status_code=502, detail="Proxmox 操作失敗")
    except Exception:
        logger.exception("Failed to sync reverse proxy rules")
        raise HTTPException(status_code=500, detail="同步反向代理規則失敗")
