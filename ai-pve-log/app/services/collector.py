"""PVE 批量資料收集服務

利用 proxmoxer 呼叫 PVE REST API，以平行方式一次性收集
所有節點、VM、LXC、儲存空間的最新資料，組成 SystemSnapshot。
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from proxmoxer import ProxmoxAPI

from app.core.config import settings
from app.schemas import (
    ClusterInfo,
    NetworkInterface,
    NodeInfo,
    ResourceConfig,
    ResourceStatus,
    ResourceSummary,
    StorageInfo,
    SystemSnapshot,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Proxmox client（singleton + 自動重連）
# ---------------------------------------------------------------------------

_proxmox_client: ProxmoxAPI | None = None
_proxmox_created_at: float = 0.0
_proxmox_lock = threading.Lock()
_TICKET_TTL = 7000  # PVE ticket 約 2 小時，提早更新


def _get_proxmox() -> ProxmoxAPI:
    global _proxmox_client, _proxmox_created_at

    if not settings.proxmox_user or not settings.proxmox_password:
        raise RuntimeError("請在 .env 設定 PROXMOX_USER 與 PROXMOX_PASSWORD")

    now = time.monotonic()
    if _proxmox_client is not None and (now - _proxmox_created_at) < _TICKET_TTL:
        return _proxmox_client

    with _proxmox_lock:
        if _proxmox_client is not None and (now - _proxmox_created_at) < _TICKET_TTL:
            return _proxmox_client

        logger.info("建立 PVE API 連線 → %s", settings.proxmox_host)
        _proxmox_client = ProxmoxAPI(
            settings.proxmox_host,
            user=settings.proxmox_user,
            password=settings.proxmox_password,
            verify_ssl=settings.proxmox_verify_ssl,
            timeout=settings.proxmox_api_timeout,
        )
        _proxmox_created_at = now
        return _proxmox_client


# ---------------------------------------------------------------------------
# 工具函式
# ---------------------------------------------------------------------------


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _safe_bool(v: Any) -> bool:
    return v in (1, "1", True, "true", "yes")


def _usage_pct(used: int, total: int) -> float:
    return round(used / total, 4) if total > 0 else 0.0


def _retry(func, *args, **kwargs):
    """簡單重試包裝器，根據設定自動重試"""
    attempts = max(settings.collector_retry_attempts, 1)
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            backoff = settings.collector_retry_backoff * (2 ** (attempt - 1))
            if backoff > 0:
                time.sleep(backoff)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 個別收集函式
# ---------------------------------------------------------------------------


def _collect_cluster_info(proxmox: ProxmoxAPI) -> ClusterInfo:
    """GET /cluster/status"""
    try:
        items = proxmox.cluster.status.get()
    except Exception:
        # 單機模式（非叢集）可能沒有 /cluster/status
        return ClusterInfo(
            cluster_name=None,
            is_cluster=False,
            node_count=1,
            quorate=True,
            cluster_version=None,
        )

    cluster_name = None
    node_count = 0
    quorate = False
    version = None

    for item in items:
        if item.get("type") == "cluster":
            cluster_name = item.get("name")
            node_count = _safe_int(item.get("nodes"), 0)
            quorate = _safe_bool(item.get("quorate"))
            version = _safe_int(item.get("version")) or None
        elif item.get("type") == "node":
            if node_count == 0:
                node_count += 1

    return ClusterInfo(
        cluster_name=cluster_name,
        is_cluster=cluster_name is not None,
        node_count=node_count if node_count > 0 else 1,
        quorate=quorate,
        cluster_version=version,
    )


def _collect_nodes(proxmox: ProxmoxAPI) -> list[NodeInfo]:
    """GET /nodes"""
    items = proxmox.nodes.get()
    result = []
    for item in items:
        mem_used = _safe_int(item.get("mem"))
        mem_total = _safe_int(item.get("maxmem"))
        disk_used = _safe_int(item.get("disk"))
        disk_total = _safe_int(item.get("maxdisk"))
        result.append(
            NodeInfo(
                node=str(item.get("node") or "unknown"),
                status=str(item.get("status") or "unknown"),
                cpu_usage=_safe_float(item.get("cpu")),
                cpu_cores=_safe_int(item.get("maxcpu")),
                mem_used_bytes=mem_used,
                mem_total_bytes=mem_total,
                mem_used_pct=_usage_pct(mem_used, mem_total),
                disk_used_bytes=disk_used,
                disk_total_bytes=disk_total,
                disk_used_pct=_usage_pct(disk_used, disk_total),
                uptime_seconds=_safe_int(item.get("uptime")) or None,
            )
        )
    return result


def _collect_storages_for_node(proxmox: ProxmoxAPI, node: str) -> list[StorageInfo]:
    """GET /nodes/{node}/storage"""
    try:
        items = proxmox.nodes(node).storage.get()
    except Exception as exc:
        logger.warning("取得節點 %s 儲存空間失敗：%s", node, exc)
        return []

    result = []
    for item in items:
        avail = _safe_int(item.get("avail"))
        used = _safe_int(item.get("used"))
        total = _safe_int(item.get("total"))
        result.append(
            StorageInfo(
                node=node,
                storage=str(item.get("storage") or item.get("id") or "unknown"),
                storage_type=str(item.get("type") or "unknown"),
                content=str(item.get("content") or ""),
                avail_bytes=avail,
                used_bytes=used,
                total_bytes=total,
                used_pct=_usage_pct(used, total),
                active=_safe_bool(item.get("active", 1)),
                enabled=not _safe_bool(item.get("disable", 0)),
                shared=_safe_bool(item.get("shared", 0)),
            )
        )
    return result


def _collect_resource_summary(item: dict) -> ResourceSummary:
    """從 cluster.resources 的單筆資料建立 ResourceSummary"""
    mem_used = _safe_int(item.get("mem"))
    mem_total = _safe_int(item.get("maxmem"))
    disk_used = _safe_int(item.get("disk"))
    disk_total = _safe_int(item.get("maxdisk"))
    return ResourceSummary(
        vmid=_safe_int(item.get("vmid")),
        name=str(item.get("name") or ""),
        resource_type=str(item.get("type") or "unknown"),
        node=str(item.get("node") or "unknown"),
        status=str(item.get("status") or "unknown"),
        pool=item.get("pool") or None,
        cpu_usage=_safe_float(item.get("cpu")),
        cpu_cores=_safe_int(item.get("maxcpu")),
        mem_used_bytes=mem_used,
        mem_total_bytes=mem_total,
        mem_used_pct=_usage_pct(mem_used, mem_total),
        disk_used_bytes=disk_used,
        disk_total_bytes=disk_total,
        disk_used_pct=_usage_pct(disk_used, disk_total),
        net_in_bytes=_safe_int(item.get("netin")),
        net_out_bytes=_safe_int(item.get("netout")),
        uptime_seconds=_safe_int(item.get("uptime")) or None,
        is_template=_safe_bool(item.get("template", 0)),
    )


def _collect_resource_status(
    proxmox: ProxmoxAPI, node: str, vmid: int, resource_type: str
) -> ResourceStatus | None:
    """GET /nodes/{node}/{type}/{vmid}/status/current"""
    try:
        if resource_type == "qemu":
            s = proxmox.nodes(node).qemu(vmid).status.current.get()
        else:
            s = proxmox.nodes(node).lxc(vmid).status.current.get()

        mem_used = _safe_int(s.get("mem"))
        mem_total = _safe_int(s.get("maxmem"))
        return ResourceStatus(
            vmid=vmid,
            node=node,
            resource_type=resource_type,
            status=str(s.get("status") or "unknown"),
            cpu_usage=_safe_float(s.get("cpu")),
            cpu_cores=_safe_int(s.get("cpus") or s.get("maxcpu")),
            mem_used_bytes=mem_used,
            mem_total_bytes=mem_total,
            mem_used_pct=_usage_pct(mem_used, mem_total),
            disk_read_bytes=_safe_int(s.get("diskread")),
            disk_write_bytes=_safe_int(s.get("diskwrite")),
            disk_total_bytes=_safe_int(s.get("maxdisk")),
            net_in_bytes=_safe_int(s.get("netin")),
            net_out_bytes=_safe_int(s.get("netout")),
            uptime_seconds=_safe_int(s.get("uptime")) or None,
            pid=_safe_int(s.get("pid")) or None,
        )
    except Exception as exc:
        logger.debug("取得 %s %d 狀態失敗：%s", resource_type, vmid, exc)
        return None


def _collect_resource_config(
    proxmox: ProxmoxAPI, node: str, vmid: int, resource_type: str
) -> ResourceConfig | None:
    """GET /nodes/{node}/{type}/{vmid}/config"""
    try:
        if resource_type == "qemu":
            c = proxmox.nodes(node).qemu(vmid).config.get()
        else:
            c = proxmox.nodes(node).lxc(vmid).config.get()

        # 解析主磁碟大小
        disk_key = "scsi0" if resource_type == "qemu" else "rootfs"
        disk_str = c.get(disk_key, "")
        disk_size_gb = None
        if "size=" in disk_str:
            size_part = disk_str.split("size=")[1].split(",")[0].strip()
            if size_part.endswith("G"):
                try:
                    disk_size_gb = int(size_part[:-1])
                except ValueError:
                    pass

        name_key = "name" if resource_type == "qemu" else "hostname"
        return ResourceConfig(
            vmid=vmid,
            node=node,
            resource_type=resource_type,
            name=c.get(name_key) or None,
            cpu_cores=_safe_int(c.get("cores") or c.get("cpus")) or None,
            cpu_type=c.get("cpu") or None,
            memory_mb=_safe_int(c.get("memory")) or None,
            disk_info=disk_str or None,
            disk_size_gb=disk_size_gb,
            os_type=c.get("ostype") or None,
            net0=c.get("net0") or None,
            description=c.get("description") or None,
            tags=c.get("tags") or None,
            onboot=_safe_bool(c.get("onboot", 0)),
            protection=_safe_bool(c.get("protection", 0)),
            raw=dict(c),
        )
    except Exception as exc:
        logger.debug("取得 %s %d 設定失敗：%s", resource_type, vmid, exc)
        return None


def _collect_lxc_interfaces(
    proxmox: ProxmoxAPI, node: str, vmid: int
) -> list[NetworkInterface]:
    """GET /nodes/{node}/lxc/{vmid}/interfaces"""
    try:
        items = proxmox.nodes(node).lxc(vmid).interfaces.get()
        result = []
        for iface in items or []:
            result.append(
                NetworkInterface(
                    vmid=vmid,
                    name=str(iface.get("name") or "unknown"),
                    inet=iface.get("inet") or None,
                    inet6=iface.get("inet6") or None,
                    hwaddr=iface.get("hwaddr") or None,
                )
            )
        return result
    except Exception as exc:
        logger.debug("取得 LXC %d 網路介面失敗：%s", vmid, exc)
        return []


# ---------------------------------------------------------------------------
# 主收集入口
# ---------------------------------------------------------------------------


def collect_snapshot() -> SystemSnapshot:
    """批量收集所有 PVE 系統資料，回傳完整 SystemSnapshot。

    執行流程：
    1. 取得叢集資訊、所有節點
    2. 平行取得各節點儲存空間
    3. 取得所有 VM/LXC 摘要
    4. 平行取得每個資源的詳細狀態（僅 running）
    5. 平行取得每個資源的設定檔（可選）
    6. 平行取得 LXC 的網路介面（可選）
    """
    started = time.monotonic()
    errors: list[str] = []
    proxmox = _get_proxmox()

    # --- 1. 叢集資訊 ---
    logger.info("收集叢集資訊...")
    try:
        cluster = _retry(_collect_cluster_info, proxmox)
    except Exception as exc:
        logger.error("收集叢集資訊失敗：%s", exc)
        errors.append(f"叢集資訊：{exc}")
        cluster = ClusterInfo(
            cluster_name=None,
            is_cluster=False,
            node_count=0,
            quorate=False,
            cluster_version=None,
        )

    # --- 2. 節點清單 ---
    logger.info("收集節點資料...")
    try:
        nodes = _retry(_collect_nodes, proxmox)
    except Exception as exc:
        logger.error("收集節點失敗：%s", exc)
        errors.append(f"節點清單：{exc}")
        nodes = []

    node_names = [n.node for n in nodes]

    # --- 3. 儲存空間（平行） ---
    logger.info("收集儲存空間資料（%d 個節點）...", len(node_names))
    storages: list[StorageInfo] = []
    with ThreadPoolExecutor(max_workers=settings.collector_max_workers) as pool:
        futures = {
            pool.submit(_retry, _collect_storages_for_node, proxmox, node): node
            for node in node_names
        }
        for future in as_completed(futures):
            try:
                storages.extend(future.result())
            except Exception as exc:
                node = futures[future]
                errors.append(f"節點 {node} 儲存空間：{exc}")

    # --- 4. 所有 VM/LXC 摘要 ---
    logger.info("收集 VM/LXC 摘要...")
    try:
        raw_resources = _retry(lambda: proxmox.cluster.resources.get(type="vm"))
    except Exception as exc:
        logger.error("收集 cluster.resources 失敗：%s", exc)
        errors.append(f"cluster.resources：{exc}")
        raw_resources = []

    all_resources: list[ResourceSummary] = []
    running_resources: list[tuple[str, int, str]] = []  # (node, vmid, type)

    for item in raw_resources:
        if _safe_bool(item.get("template", 0)):
            continue
        summary = _collect_resource_summary(item)
        all_resources.append(summary)
        if summary.status == "running":
            running_resources.append(
                (summary.node, summary.vmid, summary.resource_type)
            )

    logger.info(
        "共 %d 個資源（VM/LXC），%d 個運行中",
        len(all_resources),
        len(running_resources),
    )

    # --- 5. 詳細狀態（平行，只收 running） ---
    logger.info("收集即時狀態（%d 個 running 資源）...", len(running_resources))
    resource_statuses: list[ResourceStatus] = []
    with ThreadPoolExecutor(max_workers=settings.collector_max_workers) as pool:
        futures_status = {
            pool.submit(_retry, _collect_resource_status, proxmox, node, vmid, rtype): (
                node,
                vmid,
                rtype,
            )
            for node, vmid, rtype in running_resources
        }
        for future in as_completed(futures_status):
            try:
                result = future.result()
                if result is not None:
                    resource_statuses.append(result)
            except Exception as exc:
                node, vmid, rtype = futures_status[future]
                errors.append(f"{rtype} {vmid} 狀態：{exc}")

    # --- 6. 設定檔（平行，可選） ---
    resource_configs: list[ResourceConfig] = []
    if settings.collector_fetch_config:
        all_vmid_list = [(r.node, r.vmid, r.resource_type) for r in all_resources]
        logger.info("收集設定檔（%d 個資源）...", len(all_vmid_list))
        with ThreadPoolExecutor(max_workers=settings.collector_max_workers) as pool:
            futures_cfg = {
                pool.submit(
                    _retry, _collect_resource_config, proxmox, node, vmid, rtype
                ): (node, vmid, rtype)
                for node, vmid, rtype in all_vmid_list
            }
            for future in as_completed(futures_cfg):
                try:
                    result = future.result()
                    if result is not None:
                        resource_configs.append(result)
                except Exception as exc:
                    node, vmid, rtype = futures_cfg[future]
                    errors.append(f"{rtype} {vmid} 設定：{exc}")

    # --- 7. LXC 網路介面（平行，可選） ---
    network_interfaces: list[NetworkInterface] = []
    if settings.collector_fetch_lxc_interfaces:
        lxc_list = [
            (r.node, r.vmid)
            for r in all_resources
            if r.resource_type == "lxc" and r.status == "running"
        ]
        logger.info("收集 LXC 網路介面（%d 個容器）...", len(lxc_list))
        with ThreadPoolExecutor(max_workers=settings.collector_max_workers) as pool:
            futures_iface = {
                pool.submit(_retry, _collect_lxc_interfaces, proxmox, node, vmid): (
                    node,
                    vmid,
                )
                for node, vmid in lxc_list
            }
            for future in as_completed(futures_iface):
                try:
                    network_interfaces.extend(future.result())
                except Exception as exc:
                    node, vmid = futures_iface[future]
                    errors.append(f"LXC {vmid} 網路介面：{exc}")

    # --- 計算統計摘要 ---
    total_vms = sum(1 for r in all_resources if r.resource_type == "qemu")
    total_lxc = sum(1 for r in all_resources if r.resource_type == "lxc")
    running_vms = sum(
        1 for r in all_resources if r.resource_type == "qemu" and r.status == "running"
    )
    running_lxc = sum(
        1 for r in all_resources if r.resource_type == "lxc" and r.status == "running"
    )
    online_nodes = sum(1 for n in nodes if n.status == "online")

    duration = round(time.monotonic() - started, 3)
    logger.info(
        "收集完成：耗時 %.2f 秒，節點 %d，VM %d，LXC %d，錯誤 %d 筆",
        duration,
        len(nodes),
        total_vms,
        total_lxc,
        len(errors),
    )

    return SystemSnapshot(
        collected_at=datetime.now(timezone.utc),
        collection_duration_seconds=duration,
        cluster=cluster,
        nodes=nodes,
        storages=storages,
        resources=all_resources,
        resource_statuses=resource_statuses,
        resource_configs=resource_configs,
        network_interfaces=network_interfaces,
        errors=errors,
        total_nodes=len(nodes),
        online_nodes=online_nodes,
        total_vms=total_vms,
        total_lxc=total_lxc,
        running_vms=running_vms,
        running_lxc=running_lxc,
    )
