from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[4]
ENV_FILE = PROJECT_ROOT / ".env"


class AIAPIEnvSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    ai_api_base_url: str = "http://localhost:3000"
    ai_api_api_key: str = "ai-api-secret-key-change-me"
    ai_api_timeout: int = 120

    ai_api_rate_limit_per_minute: int = 20
    ai_api_rate_limit_window_seconds: int = 60

    redis_enabled: bool = False
    redis_url: str = "redis://localhost:6379/0"

    ai_api_public_base_url: str = "http://localhost:5000"

    @property
    def resolved_public_base_url(self) -> str:
        return self.ai_api_public_base_url.strip()

    @property
    def resolved_vllm_base_url(self) -> str:
        return self.ai_api_base_url.strip()

    @property
    def ai_api_upstream_api_key(self) -> str:
        return self.ai_api_api_key


settings = AIAPIEnvSettings()
