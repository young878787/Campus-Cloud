from __future__ import annotations

import json
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = BACKEND_ROOT.parent
ENV_FILE = BACKEND_ROOT / ".env.ai.template_recommendation"


class TemplateRecommendationSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        env_prefix="TEMPLATE_RECOMMENDATION_",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("TEMPLATE_RECOMMENDATION_ENABLED", "ENABLED"),
    )
    templates_dir: str = Field(
        default=str(PROJECT_ROOT / "frontend" / "src" / "json"),
        validation_alias=AliasChoices(
            "TEMPLATE_RECOMMENDATION_TEMPLATES_DIR",
            "TEMPLATES_DIR",
        ),
    )
    backend_node_gpu_map: str = Field(
        default="{}",
        validation_alias=AliasChoices(
            "TEMPLATE_RECOMMENDATION_BACKEND_NODE_GPU_MAP",
            "BACKEND_NODE_GPU_MAP",
        ),
    )
    vllm_base_url: str = Field(
        default="http://localhost:8000/v1",
        validation_alias=AliasChoices(
            "TEMPLATE_RECOMMENDATION_VLLM_BASE_URL",
            "VLLM_BASE_URL",
        ),
    )
    vllm_api_key: str = Field(
        default="vllm-secret-key-change-me",
        validation_alias=AliasChoices(
            "TEMPLATE_RECOMMENDATION_VLLM_API_KEY",
            "VLLM_API_KEY",
        ),
    )
    vllm_model_name: str = Field(
        default="",
        validation_alias=AliasChoices(
            "TEMPLATE_RECOMMENDATION_VLLM_MODEL_NAME",
            "VLLM_MODEL_NAME",
        ),
    )
    vllm_enable_thinking: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "TEMPLATE_RECOMMENDATION_VLLM_ENABLE_THINKING",
            "VLLM_ENABLE_THINKING",
        ),
    )
    vllm_timeout: int = Field(
        default=30,
        ge=3,
        le=300,
        validation_alias=AliasChoices(
            "TEMPLATE_RECOMMENDATION_VLLM_TIMEOUT",
            "VLLM_TIMEOUT",
        ),
    )
    vllm_temperature: float = Field(
        default=0.6,
        ge=0.0,
        le=2.0,
        validation_alias=AliasChoices(
            "TEMPLATE_RECOMMENDATION_VLLM_TEMPERATURE",
            "VLLM_TEMPERATURE",
        ),
    )
    vllm_chat_temperature: float = Field(
        default=0.9,
        ge=0.0,
        le=2.0,
        validation_alias=AliasChoices(
            "TEMPLATE_RECOMMENDATION_VLLM_CHAT_TEMPERATURE",
            "VLLM_CHAT_TEMPERATURE",
        ),
    )
    vllm_top_p: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices(
            "TEMPLATE_RECOMMENDATION_VLLM_TOP_P",
            "VLLM_TOP_P",
        ),
    )
    vllm_top_k: int = Field(
        default=20,
        ge=0,
        le=200,
        validation_alias=AliasChoices(
            "TEMPLATE_RECOMMENDATION_VLLM_TOP_K",
            "VLLM_TOP_K",
        ),
    )
    vllm_min_p: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices(
            "TEMPLATE_RECOMMENDATION_VLLM_MIN_P",
            "VLLM_MIN_P",
        ),
    )
    vllm_max_tokens: int = Field(
        default=1600,
        ge=256,
        le=300000,
        validation_alias=AliasChoices(
            "TEMPLATE_RECOMMENDATION_VLLM_MAX_TOKENS",
            "VLLM_MAX_TOKENS",
        ),
    )
    vllm_chat_max_tokens: int = Field(
        default=2048,
        ge=256,
        le=300000,
        validation_alias=AliasChoices(
            "TEMPLATE_RECOMMENDATION_VLLM_CHAT_MAX_TOKENS",
            "VLLM_CHAT_MAX_TOKENS",
        ),
    )
    vllm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        validation_alias=AliasChoices(
            "TEMPLATE_RECOMMENDATION_VLLM_PRESENCE_PENALTY",
            "VLLM_PRESENCE_PENALTY",
        ),
    )
    vllm_repetition_penalty: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        validation_alias=AliasChoices(
            "TEMPLATE_RECOMMENDATION_VLLM_REPETITION_PENALTY",
            "VLLM_REPETITION_PENALTY",
        ),
    )

    @property
    def resolved_templates_dir(self) -> Path:
        path = Path(self.templates_dir)
        if path.is_absolute():
            return path

        # Relative paths in env files should resolve from backend/, not from the
        # project root, so `../frontend/src/json` keeps working across launch dirs.
        backend_relative = (ENV_FILE.parent / path).resolve()
        if backend_relative.exists():
            return backend_relative

        return (PROJECT_ROOT / path).resolve()

    @property
    def parsed_backend_node_gpu_map(self) -> dict[str, int]:
        try:
            raw = json.loads(self.backend_node_gpu_map or "{}")
        except json.JSONDecodeError:
            return {}

        parsed: dict[str, int] = {}
        for key, value in raw.items():
            try:
                parsed[str(key)] = max(int(value), 0)
            except (TypeError, ValueError):
                continue
        return parsed


settings = TemplateRecommendationSettings()
