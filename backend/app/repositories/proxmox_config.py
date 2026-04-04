"""Proxmox 設定資料庫操作"""

from datetime import datetime, timezone

from sqlmodel import Session

from app.core.security import decrypt_value, encrypt_value
from app.models.proxmox_config import ProxmoxConfig

_SINGLETON_ID = 1


def get_proxmox_config(session: Session) -> ProxmoxConfig | None:
    return session.get(ProxmoxConfig, _SINGLETON_ID)


def upsert_proxmox_config(
    session: Session,
    host: str,
    user: str,
    password: str | None,
    verify_ssl: bool,
    iso_storage: str,
    data_storage: str,
    api_timeout: int,
    task_check_interval: int,
    pool_name: str,
    ca_cert: str | None = None,  # None=不更新，空字串=清除
    gateway_ip: str = "",
    local_subnet: str | None = None,
    default_node: str | None = None,
) -> ProxmoxConfig:
    config = session.get(ProxmoxConfig, _SINGLETON_ID)

    if config is None:
        if password is None:
            raise ValueError("初次設定必須提供密碼")
        config = ProxmoxConfig(
            id=_SINGLETON_ID,
            host=host,
            user=user,
            encrypted_password=encrypt_value(password),
            verify_ssl=verify_ssl,
            iso_storage=iso_storage,
            data_storage=data_storage,
            api_timeout=api_timeout,
            task_check_interval=task_check_interval,
            pool_name=pool_name,
            ca_cert=ca_cert if ca_cert else None,
            gateway_ip=gateway_ip or None,
            local_subnet=local_subnet or None,
            default_node=default_node or None,
        )
        session.add(config)
    else:
        config.host = host
        config.user = user
        if password is not None:
            config.encrypted_password = encrypt_value(password)
        config.verify_ssl = verify_ssl
        config.iso_storage = iso_storage
        config.data_storage = data_storage
        config.api_timeout = api_timeout
        config.task_check_interval = task_check_interval
        config.pool_name = pool_name
        if ca_cert is not None:
            config.ca_cert = ca_cert if ca_cert else None
        config.gateway_ip = gateway_ip or None
        config.local_subnet = local_subnet or None
        config.default_node = default_node or None
        config.updated_at = datetime.now(timezone.utc)
        session.add(config)

    session.commit()
    session.refresh(config)
    return config


def get_decrypted_password(config: ProxmoxConfig) -> str:
    return decrypt_value(config.encrypted_password)


__all__ = [
    "get_proxmox_config",
    "upsert_proxmox_config",
    "get_decrypted_password",
]
