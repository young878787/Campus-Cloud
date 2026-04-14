"""Cloudflare configuration persistence helpers."""

from datetime import datetime, timezone

from sqlmodel import Session

from app.core.security import decrypt_value, encrypt_value
from app.models.cloudflare_config import CloudflareConfig

_SINGLETON_ID = 1


def get_cloudflare_config(session: Session) -> CloudflareConfig | None:
    return session.get(CloudflareConfig, _SINGLETON_ID)


def upsert_cloudflare_config(
    session: Session,
    *,
    account_id: str | None,
    api_token: str,
    default_dns_target_type: str | None = None,
    default_dns_target_value: str | None = None,
) -> CloudflareConfig:
    config = get_cloudflare_config(session)
    normalized_account_id = (account_id or "").strip()
    normalized_default_dns_target_type = (default_dns_target_type or "").strip()
    normalized_default_dns_target_value = (default_dns_target_value or "").strip()
    now = datetime.now(timezone.utc)

    if config is None:
        config = CloudflareConfig(
            id=_SINGLETON_ID,
            account_id=normalized_account_id,
            encrypted_api_token=encrypt_value(api_token),
            default_dns_target_type=normalized_default_dns_target_type,
            default_dns_target_value=normalized_default_dns_target_value,
            updated_at=now,
        )
        session.add(config)
    else:
        config.account_id = normalized_account_id
        config.encrypted_api_token = encrypt_value(api_token)
        config.default_dns_target_type = normalized_default_dns_target_type
        config.default_dns_target_value = normalized_default_dns_target_value
        config.updated_at = now
        session.add(config)

    session.commit()
    session.refresh(config)
    return config


def mark_cloudflare_config_verified(
    session: Session,
    config: CloudflareConfig,
) -> CloudflareConfig:
    config.last_verified_at = datetime.now(timezone.utc)
    session.add(config)
    session.commit()
    session.refresh(config)
    return config


def get_decrypted_api_token(config: CloudflareConfig) -> str:
    return decrypt_value(config.encrypted_api_token)


__all__ = [
    "get_cloudflare_config",
    "upsert_cloudflare_config",
    "mark_cloudflare_config_verified",
    "get_decrypted_api_token",
]
