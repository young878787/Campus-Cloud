import logging
import threading
import time

from proxmoxer import ProxmoxAPI

from app.core.config import settings

from app.exceptions import ProxmoxError

logger = logging.getLogger(__name__)

_proxmox_client: ProxmoxAPI | None = None
_proxmox_created_at: float = 0.0
_proxmox_lock = threading.Lock()

PROXMOX_TICKET_TTL = 7000


def get_proxmox_api() -> ProxmoxAPI:
    global _proxmox_client, _proxmox_created_at

    now = time.monotonic()

    if _proxmox_client is not None and (now - _proxmox_created_at) < PROXMOX_TICKET_TTL:
        return _proxmox_client

    with _proxmox_lock:
        if (
            _proxmox_client is not None
            and (now - _proxmox_created_at) < PROXMOX_TICKET_TTL
        ):
            return _proxmox_client

        logger.info("Creating new Proxmox API client")
        _proxmox_client = ProxmoxAPI(
            settings.PROXMOX_HOST,
            user=settings.PROXMOX_USER,
            password=settings.PROXMOX_PASSWORD,
            verify_ssl=settings.PROXMOX_VERIFY_SSL,
            timeout=settings.PROXMOX_API_TIMEOUT,
        )
        _proxmox_created_at = time.monotonic()
        return _proxmox_client


def basic_blocking_task_status(
    node_name: str, task_id: str, check_interval: int | None = None
) -> dict:
    if check_interval is None:
        check_interval = settings.PROXMOX_TASK_CHECK_INTERVAL

    proxmox = get_proxmox_api()
    logger.info(f"Waiting for task {task_id} on node {node_name}")

    while True:
        data = proxmox.nodes(node_name).tasks(task_id).status.get()

        status = data.get("status", "")
        exitstatus = data.get("exitstatus")

        logger.debug(f"Task {task_id} status: {status}, exitstatus: {exitstatus}")

        if status == "stopped":
            if exitstatus == "OK":
                logger.info(f"Task {task_id} completed successfully")
                return data
            else:
                error_msg = f"Task {task_id} failed with exitstatus: {exitstatus}"
                logger.error(error_msg)
                raise ProxmoxError(error_msg)

        time.sleep(check_interval)
