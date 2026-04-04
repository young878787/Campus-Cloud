"""Proxmox 連線設定管理 API（僅管理員）"""

import hashlib
import logging
from typing import Any

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import Encoding
from fastapi import APIRouter, Body, HTTPException

from app.api.deps import AdminUser, SessionDep
from app.exceptions import BadRequestError
from app.repositories import proxmox_config as proxmox_config_repo
from app.repositories import proxmox_node as proxmox_node_repo
from app.repositories import proxmox_storage as proxmox_storage_repo
from app.schemas.proxmox_config import (
    CertParseResult,
    ClusterPreviewResult,
    ProxmoxConfigPublic,
    ProxmoxConfigUpdate,
    ProxmoxConnectionTestResult,
    ProxmoxNodePublic,
    ProxmoxNodeUpdate,
    ProxmoxStoragePublic,
    ProxmoxStorageUpdate,
    SyncNowResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/proxmox-config", tags=["proxmox-config"])


# ── 內部工具 ────────────────────────────────────────────────────────────────


def _cert_fingerprint(pem: str) -> str:
    """計算 PEM 憑證的 SHA-256 指紋（格式：AA:BB:CC:...）"""
    cert = x509.load_pem_x509_certificate(pem.encode(), default_backend())
    digest = hashlib.sha256(cert.public_bytes(encoding=Encoding.DER)).digest()
    return ":".join(f"{b:02X}" for b in digest)


def _to_public(config, *, is_configured: bool) -> ProxmoxConfigPublic:
    fingerprint = None
    if config.ca_cert:
        try:
            fingerprint = _cert_fingerprint(config.ca_cert)
        except Exception:
            pass
    return ProxmoxConfigPublic(
        host=config.host,
        user=config.user,
        verify_ssl=config.verify_ssl,
        iso_storage=config.iso_storage,
        data_storage=config.data_storage,
        api_timeout=config.api_timeout,
        task_check_interval=config.task_check_interval,
        pool_name=config.pool_name,
        gateway_ip=config.gateway_ip,
        local_subnet=config.local_subnet,
        default_node=config.default_node,
        updated_at=config.updated_at,
        is_configured=is_configured,
        has_ca_cert=bool(config.ca_cert),
        ca_fingerprint=fingerprint,
    )


def _node_to_public(node) -> ProxmoxNodePublic:
    return ProxmoxNodePublic(
        id=node.id,
        name=node.name,
        host=node.host,
        port=node.port,
        is_primary=node.is_primary,
        is_online=node.is_online,
        last_checked=node.last_checked,
        priority=node.priority,
    )


def _storage_to_public(s) -> ProxmoxStoragePublic:
    return ProxmoxStoragePublic(
        id=s.id,
        node_name=s.node_name,
        storage=s.storage,
        storage_type=s.storage_type,
        total_gb=s.total_gb,
        used_gb=s.used_gb,
        avail_gb=s.avail_gb,
        can_vm=s.can_vm,
        can_lxc=s.can_lxc,
        can_iso=s.can_iso,
        can_backup=s.can_backup,
        is_shared=s.is_shared,
        active=s.active,
        enabled=s.enabled,
        speed_tier=s.speed_tier,
        user_priority=s.user_priority,
    )


def _resolve_credentials(
    session,
    config_in: ProxmoxConfigUpdate,
) -> tuple[str, str | bool]:
    """
    解析連線所需的 password 與 verify_ssl/ca_cert。
    password：用請求提供的；若無則從 DB 取。
    ca_cert：用請求提供的；若無則從 DB 取。
    回傳 (password, verify_ssl_or_ca_cert_pem)。
    """
    existing = proxmox_config_repo.get_proxmox_config(session)

    # 決定密碼
    if config_in.password:
        password = config_in.password
    elif existing:
        password = proxmox_config_repo.get_decrypted_password(existing)
    else:
        raise BadRequestError("初次設定必須提供密碼")

    # 決定 CA cert / verify_ssl
    ca_cert = config_in.ca_cert
    if ca_cert is None and existing:
        ca_cert = existing.ca_cert

    if ca_cert:
        return password, ca_cert  # ca_cert PEM string
    else:
        return password, config_in.verify_ssl  # bool


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/", response_model=ProxmoxConfigPublic)
def get_proxmox_config(session: SessionDep, current_user: AdminUser) -> Any:
    """取得目前的 Proxmox 連線設定（密碼不回傳）"""
    config = proxmox_config_repo.get_proxmox_config(session)
    if config is None:
        return ProxmoxConfigPublic(
            host="",
            user="",
            verify_ssl=False,
            iso_storage="local",
            data_storage="local-lvm",
            api_timeout=30,
            task_check_interval=2,
            pool_name="CampusCloud",
            gateway_ip=None,
            local_subnet=None,
            default_node=None,
            updated_at=None,
            is_configured=False,
            has_ca_cert=False,
            ca_fingerprint=None,
        )
    return _to_public(config, is_configured=True)


@router.put("/", response_model=ProxmoxConfigPublic)
def update_proxmox_config(
    session: SessionDep, current_user: AdminUser, config_in: ProxmoxConfigUpdate
) -> Any:
    """新增或更新 Proxmox 連線設定"""
    existing = proxmox_config_repo.get_proxmox_config(session)
    if existing is None and config_in.password is None:
        raise BadRequestError("初次設定必須提供密碼")

    if config_in.ca_cert:
        try:
            x509.load_pem_x509_certificate(
                config_in.ca_cert.encode(), default_backend()
            )
        except Exception:
            raise BadRequestError("CA 憑證格式無效，請貼上正確的 PEM 格式內容")

    config = proxmox_config_repo.upsert_proxmox_config(
        session=session,
        host=config_in.host,
        user=config_in.user,
        password=config_in.password,
        verify_ssl=config_in.verify_ssl,
        iso_storage=config_in.iso_storage,
        data_storage=config_in.data_storage,
        api_timeout=config_in.api_timeout,
        task_check_interval=config_in.task_check_interval,
        pool_name=config_in.pool_name,
        ca_cert=config_in.ca_cert,
        gateway_ip=config_in.gateway_ip,
        local_subnet=config_in.local_subnet,
        default_node=config_in.default_node,
    )

    from app.core.proxmox import invalidate_proxmox_client
    invalidate_proxmox_client()

    return _to_public(config, is_configured=True)


@router.post("/preview", response_model=ClusterPreviewResult)
def preview_cluster(
    session: SessionDep,
    current_user: AdminUser,
    config_in: ProxmoxConfigUpdate,
) -> ClusterPreviewResult:
    """
    用表單內容臨時連線，偵測叢集節點。不儲存任何資料。
    前端在儲存前呼叫此 endpoint，根據回傳決定是否顯示確認 popup。
    """
    try:
        password, ssl_param = _resolve_credentials(session, config_in)

        from app.core.proxmox import _verify_server_with_ca, fetch_cluster_nodes

        # 若有 CA cert，先驗證再連線
        if isinstance(ssl_param, str):  # ca_cert PEM
            _verify_server_with_ca(config_in.host, ssl_param)
            verify_ssl: bool | str = False
        else:
            verify_ssl = ssl_param

        raw_nodes = fetch_cluster_nodes(
            host=config_in.host,
            user=config_in.user,
            password=password,
            verify_ssl=verify_ssl,
            timeout=config_in.api_timeout,
        )

        nodes = [
            ProxmoxNodePublic(
                name=n["name"],
                host=n["host"],
                port=n.get("port", 8006),
                is_primary=n.get("is_primary", False),
                is_online=True,
            )
            for n in raw_nodes
        ]
        return ClusterPreviewResult(
            success=True,
            is_cluster=len(nodes) > 1,
            nodes=nodes,
        )
    except Exception as e:
        logger.warning(f"Cluster preview failed: {e}")
        return ClusterPreviewResult(
            success=False,
            is_cluster=False,
            nodes=[],
            error="Cluster preview failed",
        )


@router.post("/sync-nodes", response_model=list[ProxmoxNodePublic])
def sync_nodes(
    session: SessionDep,
    current_user: AdminUser,
    nodes: list[ProxmoxNodePublic],
) -> list[ProxmoxNodePublic]:
    """
    將前端確認過的節點清單寫入資料庫。
    先清除舊節點再寫入新節點。
    """
    node_dicts = [
        {
            "name": n.name,
            "host": n.host,
            "port": n.port,
            "is_primary": n.is_primary,
        }
        for n in nodes
    ]
    saved = proxmox_node_repo.upsert_nodes(session, node_dicts)

    from app.core.proxmox import invalidate_proxmox_client
    invalidate_proxmox_client()

    return [_node_to_public(n) for n in saved]


@router.get("/nodes", response_model=list[ProxmoxNodePublic])
def get_nodes(session: SessionDep, current_user: AdminUser) -> list[ProxmoxNodePublic]:
    """取得所有已儲存的叢集節點清單。"""
    nodes = proxmox_node_repo.get_all_nodes(session)
    return [_node_to_public(n) for n in nodes]


@router.post("/check-nodes", response_model=list[ProxmoxNodePublic])
def check_nodes(session: SessionDep, current_user: AdminUser) -> list[ProxmoxNodePublic]:
    """
    對所有已儲存的節點做 TCP ping 健康檢查，更新 is_online 狀態後回傳最新清單。
    前端開啟 Proxmox 設定頁面時呼叫。
    """
    from app.core.proxmox import _tcp_ping

    nodes = proxmox_node_repo.get_all_nodes(session)
    for node in nodes:
        is_online = _tcp_ping(node.host, node.port)
        proxmox_node_repo.update_node_status(session, node.id, is_online)

    # 重新讀取以取得更新後的 last_checked
    nodes = proxmox_node_repo.get_all_nodes(session)
    return [_node_to_public(n) for n in nodes]


@router.put("/nodes/{node_id}", response_model=ProxmoxNodePublic)
def update_node(
    node_id: int,
    session: SessionDep,
    current_user: AdminUser,
    node_in: ProxmoxNodeUpdate,
) -> ProxmoxNodePublic:
    """更新單一節點的連線設定與優先級。"""
    node = proxmox_node_repo.update_node(
        session,
        node_id=node_id,
        host=node_in.host,
        port=node_in.port,
        priority=node_in.priority,
    )
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return _node_to_public(node)


@router.get("/storages", response_model=list[ProxmoxStoragePublic])
def get_storages(
    session: SessionDep, current_user: AdminUser
) -> list[ProxmoxStoragePublic]:
    """取得所有已儲存的 Storage 清單。"""
    storages = proxmox_storage_repo.get_all_storages(session)
    return [_storage_to_public(s) for s in storages]


@router.put("/storages/{storage_id}", response_model=ProxmoxStoragePublic)
def update_storage(
    storage_id: int,
    session: SessionDep,
    current_user: AdminUser,
    storage_in: ProxmoxStorageUpdate,
) -> ProxmoxStoragePublic:
    """更新 Storage 的使用者設定（enabled, speed_tier, user_priority）。"""
    s = proxmox_storage_repo.update_storage_settings(
        session,
        storage_id=storage_id,
        enabled=storage_in.enabled,
        speed_tier=storage_in.speed_tier,
        user_priority=storage_in.user_priority,
    )
    if s is None:
        raise HTTPException(status_code=404, detail="Storage not found")
    return _storage_to_public(s)


@router.post("/sync-now", response_model=SyncNowResult)
def sync_now(
    session: SessionDep, current_user: AdminUser
) -> SyncNowResult:
    """
    使用目前已儲存的設定連線到 Proxmox，
    自動偵測所有節點與各節點的 Storage，同步到資料庫。
    節點既有的 priority 設定會被保留。
    Storage 既有的 enabled/speed_tier/user_priority 設定會被保留。
    """
    config = proxmox_config_repo.get_proxmox_config(session)
    if config is None:
        return SyncNowResult(success=False, nodes=[], storage_count=0, error="尚未設定 Proxmox 連線資訊")

    try:
        from app.core.proxmox import _verify_server_with_ca, fetch_cluster_nodes

        password = proxmox_config_repo.get_decrypted_password(config)

        if config.ca_cert:
            _verify_server_with_ca(config.host, config.ca_cert)
            verify_ssl: bool = False
        else:
            verify_ssl = config.verify_ssl

        raw_nodes = fetch_cluster_nodes(
            host=config.host,
            user=config.user,
            password=password,
            verify_ssl=verify_ssl,
            timeout=config.api_timeout,
        )

        node_dicts = [
            {
                "name": n["name"],
                "host": n["host"],
                "port": n.get("port", 8006),
                "is_primary": n.get("is_primary", False),
            }
            for n in raw_nodes
        ]
        saved_nodes = proxmox_node_repo.upsert_nodes(session, node_dicts)

        from proxmoxer import ProxmoxAPI

        client = ProxmoxAPI(
            config.host,
            user=config.user,
            password=password,
            verify_ssl=verify_ssl,
            timeout=config.api_timeout,
        )

        storage_dicts: list[dict] = []
        for node in saved_nodes:
            try:
                raw_storages = client.nodes(node.name).storage.get()
                for st in raw_storages:
                    content = st.get("content", "")
                    total = st.get("total", 0)
                    used = st.get("used", 0)
                    avail = st.get("avail", 0)
                    storage_dicts.append({
                        "node_name": node.name,
                        "storage": st.get("storage", ""),
                        "storage_type": st.get("type"),
                        "total_gb": round(total / 1024**3, 2) if total else 0.0,
                        "used_gb": round(used / 1024**3, 2) if used else 0.0,
                        "avail_gb": round(avail / 1024**3, 2) if avail else 0.0,
                        "can_vm": "images" in content,
                        "can_lxc": "rootdir" in content,
                        "can_iso": "iso" in content,
                        "can_backup": "backup" in content,
                        "is_shared": bool(st.get("shared", 0)),
                        "active": st.get("active", 1) == 1,
                    })
            except Exception as e:
                logger.warning(f"Failed to fetch storage for node {node.name}: {e}")

        proxmox_storage_repo.upsert_storages(session, storage_dicts)

        from app.core.proxmox import invalidate_proxmox_client
        invalidate_proxmox_client()

        return SyncNowResult(
            success=True,
            nodes=[_node_to_public(n) for n in saved_nodes],
            storage_count=len(storage_dicts),
        )

    except Exception as e:
        logger.warning(f"sync-now failed: {e}")
        return SyncNowResult(success=False, nodes=[], storage_count=0, error="同步失敗，請確認連線設定")


@router.post("/parse-cert", response_model=CertParseResult)
def parse_cert(
    current_user: AdminUser,
    pem: str = Body(..., embed=True),
) -> CertParseResult:
    """解析貼上的 PEM 憑證，回傳指紋與基本資訊供管理員確認"""
    try:
        cert = x509.load_pem_x509_certificate(pem.encode(), default_backend())
        digest = hashlib.sha256(cert.public_bytes(encoding=Encoding.DER)).digest()
        fingerprint = ":".join(f"{b:02X}" for b in digest)
        return CertParseResult(
            valid=True,
            fingerprint=fingerprint,
            subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(),
            not_before=cert.not_valid_before_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
            not_after=cert.not_valid_after_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
    except Exception as e:
        logger.warning(f"Certificate parse failed: {e}")
        return CertParseResult(valid=False, error="Invalid certificate")


@router.post("/test", response_model=ProxmoxConnectionTestResult)
def test_proxmox_connection(
    session: SessionDep, current_user: AdminUser
) -> ProxmoxConnectionTestResult:
    """測試目前設定的 Proxmox 連線"""
    config = proxmox_config_repo.get_proxmox_config(session)
    if config is None:
        return ProxmoxConnectionTestResult(success=False, message="尚未設定 Proxmox 連線資訊")

    try:
        from proxmoxer import ProxmoxAPI

        from app.core.proxmox import _verify_server_with_ca

        password = proxmox_config_repo.get_decrypted_password(config)

        if config.ca_cert:
            _verify_server_with_ca(config.host, config.ca_cert)
            verify_ssl: bool = False
        else:
            verify_ssl = config.verify_ssl

        client = ProxmoxAPI(
            config.host,
            user=config.user,
            password=password,
            verify_ssl=verify_ssl,
            timeout=config.api_timeout,
        )
        nodes = client.nodes.get()
        node_names = [n.get("node", "") for n in nodes]
        return ProxmoxConnectionTestResult(
            success=True,
            message=f"連線成功，偵測到節點：{', '.join(node_names)}",
        )
    except Exception as e:
        logger.warning(f"Proxmox connection test failed: {e}")
        return ProxmoxConnectionTestResult(success=False, message="連線失敗，請檢查設定與憑證")
