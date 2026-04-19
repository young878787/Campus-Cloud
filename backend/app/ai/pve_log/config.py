from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.ai.system_config import system_ai_config, system_ai_env

PROJECT_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
        extra="ignore",
    )

    proxmox_host: str = Field(default="localhost")
    proxmox_user: str = Field(default="")
    proxmox_password: str = Field(default="")
    proxmox_verify_ssl: bool = Field(default=False)
    proxmox_api_timeout: int = Field(default=30, ge=3, le=300)

    collector_max_workers: int = Field(default=8, ge=1, le=32)
    collector_fetch_config: bool = Field(default=True)
    collector_fetch_lxc_interfaces: bool = Field(default=True)
    collector_retry_attempts: int = Field(default=3, ge=1, le=10)
    collector_retry_backoff: float = Field(default=0.3, ge=0.0, le=10.0)

    @property
    def section(self):
        return system_ai_config.pve_log

    @property
    def vllm_base_url(self) -> str:
        return system_ai_env.vllm_base_url

    @property
    def vllm_api_key(self) -> str:
        return system_ai_env.vllm_api_key

    @property
    def vllm_model_name(self) -> str:
        return system_ai_env.vllm_model_name.strip()

    @property
    def chat_timeout(self) -> int:
        return int(self.section.vllm.timeout)

    @property
    def vllm_temperature(self) -> float:
        return float(self.section.vllm.temperature)

    @property
    def vllm_max_tokens(self) -> int:
        return int(self.section.vllm.max_tokens)


settings = Settings()
