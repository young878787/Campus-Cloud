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
    port: int = Field(default=8010, ge=1, le=65535)
    api_v1_str: str = Field(default="/api/v1")
    templates_dir: str = Field(default="../frontend/src/json")
    frontend_api_base_url: str = Field(default="")
    backend_auth_email: str = Field(default="")
    backend_auth_password: str = Field(default="")
    proxmox_host: str = Field(default="")
    proxmox_user: str = Field(default="")
    proxmox_password: str = Field(default="")
    proxmox_node: str = Field(default="pve")
    proxmox_iso_storage: str = Field(default="local")
    proxmox_verify_ssl: bool = Field(default=False)
    proxmox_api_timeout: int = Field(default=15, ge=3, le=120)
    use_internal_nodes_api: bool = Field(default=True)
    backend_node_gpu_map: str = Field(default='{"pve": 1}')
    nodes_snapshot_json: str = Field(
        default='[{"node":"pve","status":"online","cpu":0.35,"maxcpu":16,"mem":30923764531,"maxmem":68719476736,"uptime":86400}]'
    )
    vllm_base_url: str = Field(default="http://localhost:8000/v1")
    vllm_api_key: str = Field(default="vllm-secret-key-change-me")
    vllm_model_name: str = Field(default="")
    vllm_enable_thinking: bool = Field(default=False)
    vllm_timeout: int = Field(default=30, ge=3, le=300)
    vllm_temperature: float = Field(default=0.6, ge=0.0, le=2.0)
    vllm_chat_temperature: float = Field(default=0.9, ge=0.0, le=2.0)
    vllm_top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    vllm_top_k: int = Field(default=20, ge=0, le=200)
    vllm_min_p: float = Field(default=0.0, ge=0.0, le=1.0)
    vllm_max_tokens: int = Field(default=1600, ge=256, le=300000)
    vllm_chat_max_tokens: int = Field(default=2048, ge=256, le=300000)
    vllm_presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    vllm_repetition_penalty: float = Field(default=1.0, ge=0.0, le=2.0)

    @property
    def resolved_templates_dir(self) -> Path:
        path = Path(self.templates_dir)
        if path.is_absolute():
            return path
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

    @property
    def parsed_nodes_snapshot(self) -> list[dict]:
        try:
            raw = json.loads(self.nodes_snapshot_json or "[]")
        except json.JSONDecodeError:
            return []
        return [item for item in raw if isinstance(item, dict)]


settings = Settings()
