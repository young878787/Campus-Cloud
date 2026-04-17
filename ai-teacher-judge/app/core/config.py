from __future__ import annotations

import json
from pydantic import Field, field_validator
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = PROJECT_ROOT.parent / "backend" / "config" / "system-ai.json"


class TeacherJudgeVLLMConfig(BaseModel):
    enable_thinking: bool = False
    timeout: int = 60
    temperature: float = 0.2
    chat_temperature: float | None = 0.7
    top_p: float = 0.95
    top_k: int = 20
    min_p: float = 0.0
    max_tokens: int = 8192
    chat_max_tokens: int | None = 4096
    repetition_penalty: float = 1.0


class TeacherJudgeSystemConfig(BaseModel):
    max_upload_size_mb: int = 10
    vllm: TeacherJudgeVLLMConfig = Field(default_factory=TeacherJudgeVLLMConfig)


def _load_teacher_judge_system_config() -> TeacherJudgeSystemConfig:
    if not CONFIG_FILE.exists():
        return TeacherJudgeSystemConfig()

    payload = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return TeacherJudgeSystemConfig()

    teacher_judge_payload = payload.get("teacher_judge") or {}
    if not isinstance(teacher_judge_payload, dict):
        return TeacherJudgeSystemConfig()

    return TeacherJudgeSystemConfig.model_validate(teacher_judge_payload)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8010, ge=1, le=65535)
    api_v1_str: str = Field(default="/api/v1")
    frontend_api_base_url: str = Field(default="")

    # Security settings
    cors_origins: str = Field(default="", description="允許的 CORS 來源，逗號分隔")

    # vLLM connection settings come from .env
    vllm_base_url: str = Field(default="http://localhost:8000/v1")
    vllm_api_key: str = Field(default="vllm-secret-key-change-me")
    vllm_model_name: str = Field(default="")

    @property
    def section(self) -> TeacherJudgeSystemConfig:
        return teacher_judge_system_config

    @property
    def max_upload_size_mb(self) -> int:
        return int(self.section.max_upload_size_mb)

    @property
    def vllm_enable_thinking(self) -> bool:
        return bool(self.section.vllm.enable_thinking)

    @property
    def vllm_timeout(self) -> int:
        return int(self.section.vllm.timeout)

    @property
    def vllm_temperature(self) -> float:
        return float(self.section.vllm.temperature)

    @property
    def vllm_chat_temperature(self) -> float:
        if self.section.vllm.chat_temperature is not None:
            return float(self.section.vllm.chat_temperature)
        return self.vllm_temperature

    @property
    def vllm_top_p(self) -> float:
        return float(self.section.vllm.top_p)

    @property
    def vllm_top_k(self) -> int:
        return int(self.section.vllm.top_k)

    @property
    def vllm_min_p(self) -> float:
        return float(self.section.vllm.min_p)

    @property
    def vllm_max_tokens(self) -> int:
        return int(self.section.vllm.max_tokens)

    @property
    def vllm_chat_max_tokens(self) -> int:
        if self.section.vllm.chat_max_tokens is not None:
            return int(self.section.vllm.chat_max_tokens)
        return self.vllm_max_tokens

    @property
    def vllm_repetition_penalty(self) -> float:
        return float(self.section.vllm.repetition_penalty)

    @field_validator('vllm_base_url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        """驗證 vLLM URL 格式。"""
        if not v.startswith(('http://', 'https://')):
            raise ValueError('vLLM URL 必須以 http:// 或 https:// 開頭')
        return v.rstrip('/')

    @property
    def max_upload_size_bytes(self) -> int:
        """取得最大上傳檔案大小（位元組）。"""
        return self.max_upload_size_mb * 1024 * 1024


teacher_judge_system_config = _load_teacher_judge_system_config()
settings = Settings()
