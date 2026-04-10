from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_PROXMOX_POOL_NAME = "CampusCloud"


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
    ca_cert: str | None = None
    local_subnet: str | None = None
    default_node: str | None = None


def get_proxmox_settings() -> ProxmoxSettings:
    """Load Proxmox settings from DB first, then fall back to env config."""
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
    except Exception as exc:
        logger.warning(
            "Unable to load Proxmox settings from database; falling back to env: %s",
            exc,
        )

    return ProxmoxSettings(
        host=settings.PROXMOX_HOST,
        user=settings.PROXMOX_USER,
        password=settings.PROXMOX_PASSWORD,
        verify_ssl=settings.PROXMOX_VERIFY_SSL,
        iso_storage=settings.PROXMOX_ISO_STORAGE,
        data_storage=settings.PROXMOX_DATA_STORAGE,
        api_timeout=settings.PROXMOX_API_TIMEOUT,
        task_check_interval=settings.PROXMOX_TASK_CHECK_INTERVAL,
        pool_name=DEFAULT_PROXMOX_POOL_NAME,
    )
