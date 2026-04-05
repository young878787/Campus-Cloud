import logging
import socket
import ssl
import threading
import time
from dataclasses import dataclass

from proxmoxer import ProxmoxAPI

from app.core.config import settings
from app.exceptions import ProxmoxError

logger = logging.getLogger(__name__)

_proxmox_client: ProxmoxAPI | None = None
_proxmox_created_at: float = 0.0
_proxmox_active_host: str | None = None   # 目前實際連線的節點 host（HA 模式下可能不等於 cfg.host）
_proxmox_lock = threading.Lock()

PROXMOX_TICKET_TTL = 7000
_TCP_PING_TIMEOUT = 2.0   # 秒，快速判斷節點是否可達


@dataclass
class ProxmoxSettings:
    host: str
    user: str
    password: str
    verify_ssl: bool
    iso_storage: str
    data_storage: str
    api_timeout: int
    task_check_interval: int
    pool_name: str
    ca_cert: str | None = None  # PEM 格式 CA 憑證原文
    local_subnet: str | None = None
    default_node: str | None = None


def _tcp_ping(host: str, port: int = 8006, timeout: float = _TCP_PING_TIMEOUT) -> bool:
    """TCP connect 到指定 host:port，成功代表主機可達。比 ICMP ping 更精準。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, ConnectionRefusedError, OSError):
        return False


def _verify_server_with_ca(host: str, ca_cert_pem: str, port: int = 8006) -> None:
    """
    用我們自己的 SSL context 驗證 Proxmox 伺服器憑證。

    不使用 ssl.create_default_context()，因為它在 Python 3.12+ 會啟用
    VERIFY_X509_STRICT，導致 PVE 自簽 CA（沒有 keyUsage extension）被拒絕。
    改用 ssl.SSLContext(PROTOCOL_TLS_CLIENT) 並手動移除 strict flag。
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cadata=ca_cert_pem)

    # Python 3.12+ 才有 VERIFY_X509_STRICT；移除後允許沒有 keyUsage 的 CA 憑證
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT

    try:
        with socket.create_connection((host, port), timeout=10) as raw_sock:
            with ctx.wrap_socket(raw_sock, server_hostname=host):
                pass  # 成功建立 TLS 連線，代表 CA 驗證通過
    except ssl.SSLCertVerificationError as e:
        raise ProxmoxError(f"CA 憑證驗證失敗，請確認貼上的憑證正確：{e}")
    except (TimeoutError, ConnectionRefusedError, OSError) as e:
        raise ProxmoxError(f"無法連線到 Proxmox 主機 {host}:{port}：{e}")


def get_proxmox_settings() -> ProxmoxSettings:
    """從資料庫載入 Proxmox 設定，若未設定則 fallback 到環境變數。"""
    try:
        from sqlmodel import Session

        from app.core.db import engine
        from app.repositories.proxmox_config import (
            get_decrypted_password,
            get_proxmox_config,
        )

        with Session(engine) as session:
            config = get_proxmox_config(session)
            if config is not None:
                return ProxmoxSettings(
                    host=config.host,
                    user=config.user,
                    password=get_decrypted_password(config),
                    verify_ssl=config.verify_ssl,
                    iso_storage=config.iso_storage,
                    data_storage=config.data_storage,
                    api_timeout=config.api_timeout,
                    task_check_interval=config.task_check_interval,
                    pool_name=config.pool_name,
                    ca_cert=config.ca_cert,
                    local_subnet=config.local_subnet,
                    default_node=config.default_node,
                )
    except Exception as e:
        logger.warning(f"無法從資料庫載入 Proxmox 設定，使用環境變數：{e}")

    return ProxmoxSettings(
        host=settings.PROXMOX_HOST,
        user=settings.PROXMOX_USER,
        password=settings.PROXMOX_PASSWORD,
        verify_ssl=settings.PROXMOX_VERIFY_SSL,
        iso_storage=settings.PROXMOX_ISO_STORAGE,
        data_storage=settings.PROXMOX_DATA_STORAGE,
        api_timeout=settings.PROXMOX_API_TIMEOUT,
        task_check_interval=settings.PROXMOX_TASK_CHECK_INTERVAL,
        pool_name="CampusCloud",
    )


def _get_nodes_for_ha() -> list:
    """
    從 DB 取得節點清單（主節點優先）。
    若 DB 無節點，回傳空清單，讓呼叫端 fallback 到 proxmox_config.host。
    """
    try:
        from sqlmodel import Session

        from app.core.db import engine
        from app.repositories.proxmox_node import get_all_nodes

        with Session(engine) as session:
            return get_all_nodes(session)
    except Exception as e:
        logger.warning(f"無法從資料庫取得節點清單：{e}")
        return []


def _update_node_online(node_id: int, is_online: bool) -> None:
    """非阻塞地更新節點狀態（忽略錯誤，不影響主流程）。"""
    try:
        from sqlmodel import Session

        from app.core.db import engine
        from app.repositories.proxmox_node import update_node_status

        with Session(engine) as session:
            update_node_status(session, node_id, is_online)
    except Exception:
        pass


def _try_connect(host: str, cfg: ProxmoxSettings) -> ProxmoxAPI:
    """
    嘗試連線到指定 host，回傳 ProxmoxAPI client。
    失敗時直接 raise exception。
    """
    if cfg.ca_cert:
        _verify_server_with_ca(host, cfg.ca_cert)
        verify_ssl: bool = False
    else:
        verify_ssl = cfg.verify_ssl

    client = ProxmoxAPI(
        host,
        user=cfg.user,
        password=cfg.password,
        verify_ssl=verify_ssl,
        timeout=cfg.api_timeout,
    )
    # 快速健康確認
    client.version.get()
    return client


def invalidate_proxmox_client() -> None:
    """強制下次呼叫時重新建立 Proxmox 客戶端（設定更新後使用）。"""
    global _proxmox_client, _proxmox_created_at, _proxmox_active_host
    with _proxmox_lock:
        _proxmox_client = None
        _proxmox_created_at = 0.0
        _proxmox_active_host = None


def get_proxmox_api() -> ProxmoxAPI:
    global _proxmox_client, _proxmox_created_at, _proxmox_active_host

    now = time.monotonic()
    if _proxmox_client is not None and (now - _proxmox_created_at) < PROXMOX_TICKET_TTL:
        return _proxmox_client

    with _proxmox_lock:
        if _proxmox_client is not None and (now - _proxmox_created_at) < PROXMOX_TICKET_TTL:
            return _proxmox_client

        cfg = get_proxmox_settings()
        nodes = _get_nodes_for_ha()

        if nodes:
            # ── HA 模式：從 DB 取得節點清單，TCP ping 後依序嘗試 ──
            last_error: Exception | None = None
            for node in nodes:
                if not _tcp_ping(node.host, node.port):
                    logger.info(f"節點 {node.name} ({node.host}) 無法 ping 通，跳過")
                    _update_node_online(node.id, False)
                    continue

                try:
                    client = _try_connect(node.host, cfg)
                    _update_node_online(node.id, True)
                    _proxmox_client = client
                    _proxmox_created_at = time.monotonic()
                    _proxmox_active_host = node.host
                    logger.info(f"已連線到 Proxmox 節點 {node.name} ({node.host})")
                    return _proxmox_client
                except Exception as e:
                    last_error = e
                    logger.warning(f"節點 {node.name} ({node.host}) 連線失敗：{e}")
                    _update_node_online(node.id, False)

            raise ProxmoxError(
                f"所有 Proxmox 節點均無法連線。最後錯誤：{last_error}"
            )
        else:
            # ── 單機模式：使用 proxmox_config.host ──
            logger.info(f"無節點記錄，使用 proxmox_config.host：{cfg.host}")
            _proxmox_client = _try_connect(cfg.host, cfg)
            _proxmox_created_at = time.monotonic()
            _proxmox_active_host = cfg.host
            return _proxmox_client


def get_active_host() -> str:
    """回傳目前實際連線的 Proxmox 節點 host（HA 模式下可能不等於 cfg.host）。
    若尚未建立連線則 fallback 到 cfg.host。
    """
    if _proxmox_active_host:
        return _proxmox_active_host
    return get_proxmox_settings().host


def build_ws_ssl_context(cfg: ProxmoxSettings) -> ssl.SSLContext:
    """
    為 WebSocket 連線建立合適的 SSL context。

    ssl.create_default_context() 在 Python 3.12+ 啟用 VERIFY_X509_STRICT 等嚴格 flag，
    即使設定 CERT_NONE 也可能導致 PVE WebSocket 握手失敗。
    改用 ssl.SSLContext(PROTOCOL_TLS_CLIENT) 並明確設定所需的驗證模式。
    """
    if cfg.ca_cert:
        # 有 CA cert：用它驗證，但移除 strict key usage 要求
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_verify_locations(cadata=cfg.ca_cert)
        if hasattr(ssl, "VERIFY_X509_STRICT"):
            ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
        return ctx
    elif cfg.verify_ssl:
        # 標準 CA 驗證
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False  # host 已由應用層確認
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_default_certs()
        return ctx
    else:
        # 不驗證（自簽憑證且未提供 CA cert）
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx


def fetch_cluster_nodes(
    host: str,
    user: str,
    password: str,
    verify_ssl: bool | str,
    timeout: int,
) -> list[dict]:
    """
    連線到指定節點，呼叫 /cluster/status 取得所有節點資訊。
    回傳格式：[{"name": str, "host": str, "port": int, "is_primary": bool}]
    單節點環境（無叢集）也能正常運作。
    """
    client = ProxmoxAPI(
        host,
        user=user,
        password=password,
        verify_ssl=verify_ssl,
        timeout=timeout,
    )

    try:
        cluster_status = client.cluster.status.get()
    except Exception:
        # 無叢集設定：只回傳這一台
        return [{"name": host, "host": host, "port": 8006, "is_primary": True}]

    nodes = []
    for item in cluster_status:
        if item.get("type") != "node":
            continue
        node_host = item.get("ip") or item.get("name")
        nodes.append(
            {
                "name": item["name"],
                "host": node_host,
                "port": 8006,
                "is_primary": (item.get("local") == 1),
            }
        )

    if not nodes:
        return [{"name": host, "host": host, "port": 8006, "is_primary": True}]

    # 確保至少有一個 primary
    if not any(n["is_primary"] for n in nodes):
        nodes[0]["is_primary"] = True

    return nodes


def basic_blocking_task_status(
    node_name: str, task_id: str, check_interval: int | None = None
) -> dict:
    if check_interval is None:
        check_interval = get_proxmox_settings().task_check_interval

    proxmox = get_proxmox_api()
    logger.info(f"Waiting for task {task_id} on node {node_name}")

    while True:
        data = proxmox.nodes(node_name).tasks(task_id).status.get()

        status = data.get("status", "")
        exitstatus = data.get("exitstatus")

        logger.debug(f"Task {task_id} status: {status}, exitstatus: {exitstatus}")

        if status == "stopped":
            if exitstatus == "OK" or (
                isinstance(exitstatus, str) and exitstatus.startswith("WARNINGS")
            ):
                if exitstatus != "OK":
                    logger.warning(
                        f"Task {task_id} completed with warnings: {exitstatus}"
                    )
                else:
                    logger.info(f"Task {task_id} completed successfully")
                return data
            else:
                error_msg = f"Task {task_id} failed with exitstatus: {exitstatus}"
                logger.error(error_msg)
                raise ProxmoxError(error_msg)

        time.sleep(check_interval)
