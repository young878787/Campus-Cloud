"""服務模板腳本部署服務

透過 SSH 連線到 Proxmox 節點，下載並以無人值守方式執行 community-scripts 腳本。
部署完成後自動刪除腳本；失敗時完全回滾（銷毀已建立的容器）。
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from sqlmodel import Session

from app.infrastructure.proxmox import (
    get_active_host,
    get_proxmox_api,
    get_proxmox_settings,
)
from app.infrastructure.ssh import (
    create_password_client,
    exec_command,
    exec_command_streaming,
)
from app.infrastructure.worker import ExpiringStore
from app.exceptions import ProxmoxError
from app.models.proxmox_config import ProxmoxConfig
from app.services.network import firewall_service
from app.services.proxmox import proxmox_service

logger = logging.getLogger(__name__)

GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main"
)


# ---------------------------------------------------------------------------
# In-memory task tracking
# ---------------------------------------------------------------------------


@dataclass
class DeploymentTask:
    task_id: str
    status: str = "running"  # running | completed | failed
    progress: str = "初始化中…"
    vmid: int | None = None
    message: str | None = None
    error: str | None = None
    output: str = ""
    user_id: str = ""
    template_name: str = ""
    created_at: datetime = field(default_factory=datetime.now)



# 已完成/失敗任務的保留時間
_TASK_TTL = timedelta(hours=2)
_TASK_STORE = ExpiringStore[DeploymentTask](
    ttl=_TASK_TTL,
    is_expired=lambda task, now, ttl: task.status in {"completed", "failed"}
    and now - task.created_at > ttl,
)


def _store_task(task: DeploymentTask) -> None:
    _TASK_STORE.upsert(task.task_id, task)


def get_task(task_id: str) -> DeploymentTask | None:
    return _TASK_STORE.get(task_id)


# ---------------------------------------------------------------------------
# SSH helpers
# ---------------------------------------------------------------------------


def _ssh_connect():
    """建立到 Proxmox 節點的 SSH 連線。"""
    cfg = get_proxmox_settings()
    host = get_active_host()
    ssh_user = cfg.user.split("@")[0] if "@" in cfg.user else cfg.user

    return create_password_client(
        host,
        22,
        ssh_user,
        cfg.password,
        timeout=30,
        host_key_policy="warning",
    )


def _ssh_exec(client, command: str, timeout: int = 600) -> tuple[int, str, str]:
    return exec_command(client, command, timeout=timeout)


def _ssh_exec_streaming(
    client,
    command: str,
    task: "DeploymentTask",
    timeout: int = 900,
) -> tuple[int, str, str]:
    stdout_chunks: list[str] = []

    def _on_stdout(chunk: str) -> None:
        stdout_chunks.append(chunk)
        task.output = "".join(stdout_chunks)
        _store_task(task)

    return exec_command_streaming(
        client,
        command,
        timeout=timeout,
        on_stdout=_on_stdout,
    )


# ---------------------------------------------------------------------------
# VMID detection
# ---------------------------------------------------------------------------


def _get_all_vmids() -> set[int]:
    """取得目前所有 VM/CT 的 VMID 集合（不限 pool）。"""
    try:
        proxmox = get_proxmox_api()
        resources = proxmox.cluster.resources.get(type="vm")
        return {r["vmid"] for r in resources}
    except Exception:
        return set()


def _find_new_vmid(before: set[int]) -> int | None:
    """比較部署前後的 VMID 差異，找出新建的容器。"""
    after = _get_all_vmids()
    new_ids = after - before
    if new_ids:
        return max(new_ids)
    return None


def _find_vmid_by_hostname(hostname: str) -> int | None:
    """透過 hostname 在所有叢集資源中尋找 VMID。"""
    try:
        proxmox = get_proxmox_api()
        all_resources = proxmox.cluster.resources.get(type="vm")
        for r in all_resources:
            if r.get("name") == hostname:
                return r["vmid"]
    except Exception:
        logger.warning("透過 hostname 尋找 VMID 失敗: %s", hostname)
    return None


# ---------------------------------------------------------------------------
# Post-deployment setup
# ---------------------------------------------------------------------------


def _find_resource_any(vmid: int) -> dict | None:
    """不限 pool 地查找資源，回傳含 node 和 type 的 dict。"""
    try:
        proxmox = get_proxmox_api()
        for r in proxmox.cluster.resources.get(type="vm"):
            if r["vmid"] == vmid:
                return r
    except Exception:
        pass
    return None


def _add_to_pool(vmid: int) -> None:
    """將容器加入 Campus Cloud Pool。"""
    pool_name = get_proxmox_settings().pool_name
    proxmox = get_proxmox_api()
    proxmox.pools(pool_name).put(vms=str(vmid))
    logger.info("已將 VMID=%s 加入 Pool %s", vmid, pool_name)


def _clear_description(vmid: int) -> None:
    """清除 community-scripts 自動產生的 description/notes。"""
    resource = _find_resource_any(vmid)
    if resource is None:
        logger.warning("找不到 VMID=%s 的資源，略過清除 description", vmid)
        return
    node = resource["node"]
    rtype = resource["type"]
    proxmox_service.update_config(node, vmid, rtype, description="")
    logger.info("已清除 VMID=%s 的 description", vmid)


def _apply_default_firewall(vmid: int) -> None:
    """對新部署的容器套用預設防火牆規則。"""
    resource = _find_resource_any(vmid)
    if resource is None:
        logger.warning("找不到 VMID=%s 的資源，略過防火牆設定", vmid)
        return
    node = resource["node"]
    rtype = resource["type"]  # "lxc" or "qemu"
    firewall_service.setup_default_rules(node, vmid, rtype)
    logger.info("已對 VMID=%s (%s) 套用預設防火牆規則", vmid, rtype)


# ---------------------------------------------------------------------------
# Cleanup / rollback
# ---------------------------------------------------------------------------


def _destroy_container(vmid: int) -> None:
    """銷毀失敗的容器（最大努力）。"""
    try:
        resource = proxmox_service.find_resource(vmid)
        node = resource["node"]
        rtype = resource["type"]

        try:
            status = proxmox_service.get_status(node, vmid, rtype)
            if status.get("status") == "running":
                proxmox_service.control(node, vmid, rtype, "stop")
        except Exception:
            pass

        delete_params: dict[str, int] = {"purge": 1}
        if rtype == "qemu":
            delete_params["destroy-unreferenced-disks"] = 1
        proxmox_service.delete_resource(node, vmid, rtype, **delete_params)
        logger.info("已清除失敗部署的容器 VMID=%s", vmid)
    except Exception:
        logger.exception("清除容器 VMID=%s 失敗", vmid)


def _cleanup_script_on_node(client, script_path: str) -> None:
    """刪除 Proxmox 節點上的暫存腳本。"""
    try:
        _ssh_exec(client, f"rm -f {script_path}")
        logger.info("已刪除暫存腳本: %s", script_path)
    except Exception:
        logger.warning("刪除暫存腳本失敗: %s", script_path)


# ---------------------------------------------------------------------------
# Main deployment logic
# ---------------------------------------------------------------------------


def _get_storage_settings() -> tuple[str, str]:
    """從資料庫讀取 Proxmox storage 設定，回傳 (iso_storage, data_storage)。"""
    from app.core.db import engine

    with Session(engine) as session:
        config = session.get(ProxmoxConfig, 1)
        if config:
            return config.iso_storage, config.data_storage
    return "local", "local-lvm"


def _build_inline_env(
    hostname: str,
    password: str,
    cpu: int,
    ram: int,
    disk: int,
    unprivileged: bool,
    ssh: bool,
    template_storage: str = "local",
    container_storage: str = "local-lvm",
) -> str:
    r"""產生 inline 環境變數字串（官方 community-scripts 模式）。

    官方用法：var_cpu=4 var_ram=4096 ... bash -c "\$(curl ...)"
    變數以空格分隔放在 bash -c 前面，讓 shell 直接設定到同一進程。
    密碼用單引號包裹以避免特殊字元問題。
    """
    # 密碼用單引號，內部的單引號用 '\'' 轉義
    safe_password = password.replace("'", "'\\''")
    parts = [
        "TERM=xterm",
        "mode=generated",
        f"var_hostname='{hostname}'",
        f"var_password='{safe_password}'",
        f"var_cpu={cpu}",
        f"var_ram={ram}",
        f"var_disk={disk}",
        f"var_unprivileged={1 if unprivileged else 0}",
        "var_net='dhcp'",
        f"var_ssh={'yes' if ssh else 'no'}",
        "var_tags=''",
        "var_ipv6_method='none'",
        f"var_template_storage='{template_storage}'",
        f"var_container_storage='{container_storage}'",
    ]
    return " ".join(parts)


def _run_deployment(task: DeploymentTask, request_data: dict) -> None:  # noqa: C901
    """在背景執行緒中執行腳本部署。"""
    client = None
    temp_script = f"/tmp/campus-cloud-deploy-{task.task_id}.sh"
    vmids_before = _get_all_vmids()
    new_vmid: int | None = None

    try:
        # 1. SSH 連線
        task.progress = "正在連線到 Proxmox 節點…"
        _store_task(task)
        client = _ssh_connect()
        logger.info("SSH 連線成功，開始部署 %s", request_data["script_path"])

        # 2. 下載腳本到暫存檔
        task.progress = "正在下載部署腳本…"
        _store_task(task)

        script_url = f"{GITHUB_RAW_BASE}/{request_data['script_path']}"
        download_cmd = f'curl -fsSL -o {temp_script} "{script_url}"'
        exit_code, stdout, stderr = _ssh_exec(client, download_cmd, timeout=60)
        if exit_code != 0:
            raise RuntimeError(f"下載腳本失敗: {stderr}")

        # 2.5 組合 inline 環境變數（官方 community-scripts 模式）
        task.progress = "正在設定無人值守參數…"
        _store_task(task)

        iso_storage, data_storage = _get_storage_settings()
        logger.info("Storage 設定: template=%s, container=%s", iso_storage, data_storage)

        inline_env = _build_inline_env(
            hostname=request_data["hostname"],
            password=request_data["password"],
            cpu=request_data["cpu"],
            ram=request_data["ram"],
            disk=request_data["disk"],
            unprivileged=request_data["unprivileged"],
            ssh=request_data["ssh"],
            template_storage=iso_storage,
            container_storage=data_storage,
        )

        # 3. 以官方模式執行：VAR=value bash -c "$(cat script)"
        task.progress = "正在執行無人值守部署（可能需要幾分鐘）…"
        _store_task(task)

        deploy_cmd = f'{inline_env} bash -c "$(cat {temp_script})"'
        # 注意：不記錄完整的 deploy_cmd，以免敏感資訊（例如密碼）洩漏到日誌
        logger.info("開始執行無人值守部署腳本: %s", request_data["script_path"])
        exit_code, stdout, stderr = _ssh_exec_streaming(
            client, deploy_cmd, task, timeout=900
        )

        task.output = stdout
        if stderr:
            task.output += f"\n--- STDERR ---\n{stderr}"

        # 4. 清除暫存檔案
        task.progress = "正在清除暫存檔案…"
        _store_task(task)
        _cleanup_script_on_node(client, temp_script)

        # 5. 檢查執行結果
        if exit_code != 0:
            raise RuntimeError(
                f"腳本執行失敗 (exit code {exit_code}):\n{stderr or stdout}"
            )

        # 6. 找出新建的 VMID
        task.progress = "正在確認部署結果…"
        _store_task(task)

        new_vmid = _find_new_vmid(vmids_before)
        if new_vmid is None:
            new_vmid = _find_vmid_by_hostname(request_data["hostname"])

        if new_vmid is None:
            raise RuntimeError(
                "腳本執行完成但無法找到新建的容器。請檢查 Proxmox 控制台。"
            )

        # 7. 加入 Campus Cloud Pool
        task.progress = "正在加入 Campus Cloud 集區…"
        _store_task(task)
        try:
            _add_to_pool(new_vmid)
        except Exception as e:
            logger.warning("加入 Pool 失敗 (非致命): %s", e)

        # 8. 套用預設防火牆規則
        task.progress = "正在套用預設防火牆規則…"
        _store_task(task)
        try:
            _apply_default_firewall(new_vmid)
        except Exception as e:
            logger.warning("套用防火牆規則失敗 (非致命): %s", e)

        # 9. 清除 community-scripts 自動產生的 description
        try:
            _clear_description(new_vmid)
        except Exception as e:
            logger.warning("清除 description 失敗 (非致命): %s", e)

        task.vmid = new_vmid
        task.status = "completed"
        task.progress = "部署完成"
        task.message = (
            f"服務 {request_data['template_slug']} 已成功部署，"
            f"VMID: {new_vmid}，主機名稱: {request_data['hostname']}"
        )
        _store_task(task)
        logger.info(
            "部署成功: template=%s, vmid=%s",
            request_data["template_slug"],
            new_vmid,
        )

    except Exception as e:
        error_msg = str(e)
        logger.error("部署失敗: %s", error_msg)

        # 回滾：清除暫存檔案
        if client:
            _cleanup_script_on_node(client, temp_script)

        # 回滾：銷毀已建立的容器
        rollback_vmid = new_vmid or _find_new_vmid(vmids_before)
        if rollback_vmid is None:
            rollback_vmid = _find_vmid_by_hostname(request_data["hostname"])

        if rollback_vmid:
            logger.info("回滾：正在銷毀容器 VMID=%s", rollback_vmid)
            _destroy_container(rollback_vmid)
            error_msg += f"\n已自動回滾：銷毀了部分建立的容器 (VMID: {rollback_vmid})"

        task.status = "failed"
        task.error = error_msg
        task.progress = "部署失敗，已回滾"
        _store_task(task)

    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass


def start_deployment(
    request_data: dict,
    user_id: str,
) -> str:
    """啟動背景部署任務，回傳 task_id。"""
    task_id = str(uuid.uuid4())
    task = DeploymentTask(
        task_id=task_id,
        user_id=user_id,
        template_name=request_data.get("os_info") or request_data.get("template_slug", ""),
    )
    _store_task(task)

    thread = threading.Thread(
        target=_run_deployment,
        args=(task, request_data),
        daemon=True,
        name=f"deploy-{task_id[:8]}",
    )
    thread.start()

    return task_id
