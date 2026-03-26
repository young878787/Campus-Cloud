from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = BACKEND_ROOT / ".env.ai.pve_advisor"


class PVEAdvisorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        env_prefix="PVE_ADVISOR_",
        case_sensitive=False,
        extra="ignore",
    )

    enabled: bool = Field(default=True)
    source_cache_ttl_seconds: int = Field(default=20, ge=0, le=300)
    backend_node_gpu_map: str = Field(default="{}")

    backend_traffic_window_minutes: int = Field(default=60, ge=5, le=1440)
    backend_traffic_sample_limit: int = Field(default=200, ge=20, le=1000)
    backend_pending_high_threshold: int = Field(default=20, ge=1, le=10000)

    audit_log_window_minutes: int = Field(default=120, ge=5, le=10080)
    audit_log_sample_limit: int = Field(default=300, ge=20, le=5000)
    audit_log_burst_threshold: int = Field(default=40, ge=1, le=100000)

    aggregation_stair_coefficient: float = Field(default=1.2, ge=1.01, le=5.0)
    cpu_high_threshold: float = Field(default=0.85, ge=0.0, le=1.5)
    memory_high_threshold: float = Field(default=0.85, ge=0.0, le=1.5)
    disk_high_threshold: float = Field(default=0.9, ge=0.0, le=1.5)
    guest_pressure_threshold: float = Field(default=0.85, ge=0.1, le=3.0)
    guest_per_core_limit: float = Field(default=2.0, ge=0.1, le=20.0)
    safe_users_per_cpu: float = Field(default=35.0, ge=1.0, le=10000.0)
    safe_users_per_gib: float = Field(default=20.0, ge=1.0, le=10000.0)
    placement_headroom_ratio: float = Field(default=0.1, ge=0.0, le=0.5)
    placement_weight_cpu: float = Field(default=0.35, ge=0.0, le=1.0)
    placement_weight_memory: float = Field(default=0.35, ge=0.0, le=1.0)
    placement_weight_disk: float = Field(default=0.15, ge=0.0, le=1.0)
    placement_weight_guest: float = Field(default=0.15, ge=0.0, le=1.0)

    vllm_base_url: str = Field(default="http://localhost:8000/v1")
    vllm_api_key: str = Field(default="vllm-secret-key-change-me")
    vllm_model_name: str = Field(default="")
    vllm_enable_thinking: bool = Field(default=False)
    vllm_timeout: int = Field(default=30, ge=3, le=300)
    vllm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    vllm_top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    vllm_top_k: int = Field(default=20, ge=0, le=200)
    vllm_min_p: float = Field(default=0.0, ge=0.0, le=1.0)
    vllm_max_tokens: int = Field(default=900, ge=128, le=300000)
    vllm_repetition_penalty: float = Field(default=1.0, ge=0.0, le=2.0)

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


settings = PVEAdvisorSettings()
