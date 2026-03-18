from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8011, ge=1, le=65535)
    api_v1_str: str = Field(default="/api/v1")
    frontend_api_base_url: str = Field(default="")

    use_direct_proxmox: bool = Field(default=True)
    proxmox_host: str = Field(default="localhost")
    proxmox_user: str = Field(default="")
    proxmox_password: str = Field(default="")
    proxmox_verify_ssl: bool = Field(default=False)
    proxmox_api_timeout: int = Field(default=30, ge=3, le=300)

    backend_node_gpu_map: str = Field(default="{}")
    nodes_snapshot_json: str = Field(default="[]")
    token_usage_snapshot_json: str = Field(default="[]")
    gpu_metrics_snapshot_json: str = Field(default="[]")

    aggregation_stair_coefficient: float = Field(default=1.2, ge=1.01, le=5.0)

    cpu_high_threshold: float = Field(default=0.85, ge=0.0, le=1.5)
    memory_high_threshold: float = Field(default=0.85, ge=0.0, le=1.5)
    disk_high_threshold: float = Field(default=0.9, ge=0.0, le=1.5)
    guest_pressure_threshold: float = Field(default=0.85, ge=0.1, le=3.0)
    guest_per_core_limit: float = Field(default=2.0, ge=0.1, le=20.0)
    safe_users_per_cpu: float = Field(default=35.0, ge=1.0, le=10000.0)
    safe_users_per_gib: float = Field(default=20.0, ge=1.0, le=10000.0)
    token_spike_ratio: float = Field(default=1.5, ge=1.0, le=20.0)
    placement_headroom_ratio: float = Field(default=0.1, ge=0.0, le=0.5)

    vllm_base_url: str = Field(default="http://localhost:8000")
    vllm_api_key: str = Field(default="vllm-secret-key-change-me")
    vllm_model_name: str = Field(default="")
    vllm_timeout: int = Field(default=10, ge=3, le=300)

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

    @property
    def parsed_nodes_snapshot(self) -> list[dict]:
        return _parse_dict_list(self.nodes_snapshot_json)

    @property
    def parsed_token_usage_snapshots(self) -> list[dict]:
        return _parse_dict_list(self.token_usage_snapshot_json)

    @property
    def parsed_gpu_metric_snapshots(self) -> list[dict]:
        return _parse_dict_list(self.gpu_metrics_snapshot_json)


def _parse_dict_list(payload: str) -> list[dict]:
    try:
        raw = json.loads(payload or "[]")
    except json.JSONDecodeError:
        return []
    return [item for item in raw if isinstance(item, dict)]


settings = Settings()
