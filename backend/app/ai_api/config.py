from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


class AIAPIEnvSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # VLLM Gateway 配置（内网地址）
    ai_api_base_url: str = "http://localhost:3000"
    ai_api_api_key: str = "ai-api-secret-key-change-me"
    ai_api_timeout: int = 120

    # 速率限制配置
    ai_api_rate_limit_per_minute: int = 20
    ai_api_rate_limit_window_seconds: int = 60

    # Redis 配置
    redis_enabled: bool = False  # 是否啟用 Redis 監控（開發環境建議設為 False）
    redis_url: str = "redis://localhost:6379/0"

    # 公共 API 地址（用户访问，内网环境可以使用 localhost）
    ai_api_public_base_url: str = "http://localhost:5000"

    @property
    def resolved_public_base_url(self) -> str:
        """返回用户访问的公共 API 地址"""
        return self.ai_api_public_base_url.strip()

    @property
    def resolved_vllm_base_url(self) -> str:
        """返回 VLLM Gateway 的内网地址"""
        return self.ai_api_base_url.strip()


settings = AIAPIEnvSettings()
