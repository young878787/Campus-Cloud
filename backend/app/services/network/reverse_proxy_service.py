"""反向代理服務 — 透過 Gateway VM 的 Traefik 管理 domain → VM 映射。

設計原則：
- DB 為 source of truth
- 每次新增 / 刪除後，從 DB 完整重建 Traefik dynamic config（YAML）
- Traefik 的 file provider 設定 watch: true，寫入後自動生效，無需 reload
- dns_provider 欄位預留給 Cloudflare 等 DNS API 對接
"""

import logging

import yaml

from app.exceptions import BadRequestError, ProxmoxError

logger = logging.getLogger(__name__)


# ─── Traefik dynamic config 產生 ───────────────────────────────────────────────


def _build_traefik_dynamic_config(rules: list) -> str:
    """從 DB 規則列表產生 Traefik dynamic config YAML。"""
    routers: dict = {}
    services: dict = {}

    for r in rules:
        safe_name = f"cc-{r.vmid}-{r.domain.replace('.', '-')}"

        router: dict = {
            "rule": f"Host(`{r.domain}`)",
            "service": f"{safe_name}-svc",
            "entryPoints": ["websecure"] if r.enable_https else ["web"],
        }
        if r.enable_https:
            router["tls"] = {"certResolver": "letsencrypt"}

        routers[safe_name] = router

        services[f"{safe_name}-svc"] = {
            "loadBalancer": {
                "servers": [{"url": f"http://{r.vm_ip}:{r.internal_port}"}],
            }
        }

    config: dict = {
        "http": {
            "routers": routers if routers else {},
            "services": services if services else {},
        }
    }

    header = (
        "# Campus Cloud 自動管理的反向代理設定\n"
        "# 此檔案由 Campus Cloud 自動維護，請勿手動修改\n\n"
    )
    return header + yaml.dump(config, default_flow_style=False, allow_unicode=True)


# ─── Traefik 同步（核心）──────────────────────────────────────────────────────


def _sync_traefik(session: object) -> None:
    """從 DB 重建 Traefik dynamic config 並寫入 Gateway VM。
    Traefik file provider 設定 watch: true，寫入即生效。
    """
    from app.repositories import gateway_config as gw_repo  # noqa: PLC0415
    from app.repositories import reverse_proxy as rp_repo  # noqa: PLC0415
    from app.repositories.gateway_config import get_decrypted_private_key  # noqa: PLC0415
    from app.infrastructure.ssh import create_key_client, exec_command  # noqa: PLC0415
    from app.services.network.gateway_service import TRAEFIK_DYNAMIC_PATH  # noqa: PLC0415

    config = gw_repo.get_gateway_config(session)  # type: ignore[arg-type]
    if config is None or not config.host or not config.encrypted_private_key:
        raise ProxmoxError("Gateway VM 尚未設定，無法同步 Traefik 規則")

    rules = rp_repo.list_rules(session)  # type: ignore[arg-type]
    private_key_pem = get_decrypted_private_key(config)  # type: ignore[arg-type]

    new_cfg = _build_traefik_dynamic_config(rules)
    tmp_path = TRAEFIK_DYNAMIC_PATH + ".tmp"

    client = create_key_client(
        config.host,
        config.ssh_port,
        config.ssh_user,
        private_key_pem,
    )
    try:
        # 確保目錄存在
        exec_command(client, f"mkdir -p $(dirname {TRAEFIK_DYNAMIC_PATH})")

        # 原子性寫入
        sftp = client.open_sftp()
        try:
            with sftp.open(tmp_path, "w") as f:
                f.write(new_cfg.encode())
        finally:
            sftp.close()

        code, out, err = exec_command(client, f"mv {tmp_path} {TRAEFIK_DYNAMIC_PATH}")
        if code != 0:
            raise ProxmoxError(f"Traefik 設定寫入失敗：{out}{err}")

        logger.info(f"[ReverseProxy] Traefik 已同步 {len(rules)} 條 domain 規則")
    except ProxmoxError:
        raise
    except Exception as e:
        raise ProxmoxError(f"Traefik 同步失敗：{e}")
    finally:
        client.close()


# ─── 公開操作 ──────────────────────────────────────────────────────────────────


def apply_reverse_proxy_rule(
    session: object,
    vmid: int,
    vm_ip: str,
    domain: str,
    internal_port: int,
    enable_https: bool = True,
) -> None:
    """建立反向代理規則：寫入 DB + 同步 Traefik。"""
    from app.models.reverse_proxy_rule import ReverseProxyRule  # noqa: PLC0415
    from app.repositories import reverse_proxy as rp_repo  # noqa: PLC0415

    # 驗證 domain 格式
    domain = domain.strip().lower()
    if not domain or " " in domain:
        raise BadRequestError("網域名稱格式不正確")

    if rp_repo.is_domain_taken(session, domain):  # type: ignore[arg-type]
        raise BadRequestError(f"網域 {domain} 已被其他 VM 佔用")

    rule = ReverseProxyRule(
        vmid=vmid,
        vm_ip=vm_ip,
        domain=domain,
        internal_port=internal_port,
        enable_https=enable_https,
    )
    rp_repo.create_rule(session, rule)  # type: ignore[arg-type]
    _sync_traefik(session)


def remove_reverse_proxy_rule_by_id(session: object, rule_id: str) -> None:
    """刪除指定反向代理規則。"""
    import uuid as _uuid  # noqa: PLC0415

    from app.repositories import reverse_proxy as rp_repo  # noqa: PLC0415

    rule = rp_repo.get_rule(session, _uuid.UUID(rule_id))  # type: ignore[arg-type]
    if rule is None:
        raise BadRequestError(f"反向代理規則 {rule_id} 不存在")

    rp_repo.delete_rule(session, rule)  # type: ignore[arg-type]
    _sync_traefik(session)


def remove_reverse_proxy_rules_for_vmid(session: object, vmid: int) -> None:
    """刪除指定 VM 的所有反向代理規則。"""
    from app.repositories import reverse_proxy as rp_repo  # noqa: PLC0415

    deleted = rp_repo.delete_rules_by_vmid(session, vmid)  # type: ignore[arg-type]
    if deleted:
        _sync_traefik(session)


def remove_reverse_proxy_rules_by_internal_port(
    session: object, vmid: int, internal_port: int
) -> None:
    """刪除指定 VM 特定內部 port 的反向代理規則。"""
    from app.repositories import reverse_proxy as rp_repo  # noqa: PLC0415

    deleted = rp_repo.delete_rules_by_vmid_and_port(  # type: ignore[arg-type]
        session, vmid, internal_port
    )
    if deleted:
        _sync_traefik(session)


def sync_to_gateway(session: object) -> None:
    """手動觸發 Traefik 同步。"""
    _sync_traefik(session)
