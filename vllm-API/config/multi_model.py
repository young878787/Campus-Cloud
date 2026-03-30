"""多模型與 Gateway 設定載入工具。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

from config.settings import PROJECT_ROOT, Settings

DEFAULT_BASE_ENV = ".env"
DEFAULT_GATEWAY_ENV = ".env.gateway"


@dataclass(frozen=True)
class ModelInstanceConfig:
    """單一模型實例設定。"""

    alias: str
    env_file: Path
    settings: Settings

    @property
    def upstream_host(self) -> str:
        if self.settings.api_host in {"0.0.0.0", "::"}:
            return "127.0.0.1"
        return self.settings.api_host

    @property
    def upstream_base_url(self) -> str:
        return f"http://{self.upstream_host}:{self.settings.api_port}/v1"


@dataclass(frozen=True)
class GatewayConfig:
    """Gateway 運行設定。"""

    host: str
    port: int
    request_timeout: int
    max_inflight: int
    default_model: str


@dataclass(frozen=True)
class GatewayRoute:
    """Gateway 路由目標。"""

    alias: str
    model_name: str
    base_url: str
    api_key: str


def _resolve_env_path(env_file: str | Path) -> Path:
    path = Path(env_file)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _resolve_gateway_env_path(gateway_env_file: str | Path) -> Path:
    """解析 gateway env 路徑（不啟用回退）。"""
    return _resolve_env_path(gateway_env_file)


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | None, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    return int(value)


def _parse_model_env_files(gateway_env: dict[str, str]) -> list[Path]:
    raw = gateway_env.get("GATEWAY_MODEL_ENV_FILES", "")
    if not raw.strip():
        raise ValueError("GATEWAY_MODEL_ENV_FILES 缺失，請在 .env.gateway 明確指定模型設定檔清單")
    return [_resolve_env_path(p.strip()) for p in raw.split(",") if p.strip()]


def load_gateway_config(gateway_env_file: str | Path = DEFAULT_GATEWAY_ENV) -> GatewayConfig:
    """載入 Gateway 設定。"""
    env_path = _resolve_gateway_env_path(gateway_env_file)
    if not env_path.exists():
        raise FileNotFoundError(f"Gateway 設定檔不存在: {env_path}")
    gateway_env = dotenv_values(env_path)

    default_model = gateway_env.get("GATEWAY_DEFAULT_MODEL", "")
    return GatewayConfig(
        host=str(gateway_env.get("GATEWAY_HOST", "0.0.0.0") or "0.0.0.0"),
        port=_parse_int(gateway_env.get("GATEWAY_PORT"), 3000),
        request_timeout=_parse_int(gateway_env.get("GATEWAY_REQUEST_TIMEOUT"), 300),
        max_inflight=_parse_int(gateway_env.get("GATEWAY_MAX_INFLIGHT"), 48),
        default_model=str(default_model or ""),
    )


def load_model_instances(
    base_env_file: str | Path = ".env",
    gateway_env_file: str | Path = DEFAULT_GATEWAY_ENV,
) -> list[ModelInstanceConfig]:
    """載入多模型實例設定。"""
    base_path = _resolve_env_path(base_env_file)
    gateway_path = _resolve_gateway_env_path(gateway_env_file)
    if not base_path.exists():
        raise FileNotFoundError(f"集群共用設定檔不存在: {base_path}")
    if not gateway_path.exists():
        raise FileNotFoundError(f"Gateway 設定檔不存在: {gateway_path}")
    gateway_env = dotenv_values(gateway_path)
    model_env_files = _parse_model_env_files(gateway_env)

    instances: list[ModelInstanceConfig] = []
    seen_alias: set[str] = set()
    seen_port: set[int] = set()

    for model_env_file in model_env_files:
        if not model_env_file.exists():
            raise FileNotFoundError(f"模型設定檔不存在: {model_env_file}")

        model_env = dotenv_values(model_env_file)
        alias = model_env.get("MODEL_ALIAS", "").strip()
        if not alias:
            raise ValueError(f"MODEL_ALIAS 缺失: {model_env_file}")
        if alias in seen_alias:
            raise ValueError(f"MODEL_ALIAS 重複: {alias}")

        settings = Settings(
            _env_file=[str(base_path), str(model_env_file)],
            _env_file_encoding="utf-8",
        )

        if settings.api_port in seen_port:
            raise ValueError(f"API_PORT 重複: {settings.api_port} ({model_env_file})")

        seen_alias.add(alias)
        seen_port.add(settings.api_port)

        instances.append(
            ModelInstanceConfig(
                alias=alias,
                env_file=model_env_file,
                settings=settings,
            )
        )

    return instances


def build_gateway_routes(instances: list[ModelInstanceConfig]) -> dict[str, GatewayRoute]:
    """由模型實例建立 Gateway 路由表。"""
    routes: dict[str, GatewayRoute] = {}
    for instance in instances:
        routes[instance.alias] = GatewayRoute(
            alias=instance.alias,
            model_name=instance.settings.resolved_model_path,
            base_url=instance.upstream_base_url,
            api_key=instance.settings.api_key,
        )
    return routes


def validate_cluster_resources(instances: list[ModelInstanceConfig]) -> None:
    """驗證多模型資源配置，避免明顯 OOM。"""
    total_gpu_util = sum(i.settings.gpu_memory_utilization for i in instances)
    hard_limit = float(os.getenv("CLUSTER_GPU_UTIL_HARD_LIMIT", "0.95"))
    if total_gpu_util >= hard_limit:
        raise ValueError(
            "三模型 GPU_MEMORY_UTILIZATION 總和過高: "
            f"{total_gpu_util:.2f} >= {hard_limit:.2f}"
        )


def find_route_for_model(
    model: str,
    routes: dict[str, GatewayRoute],
) -> GatewayRoute | None:
    """依 alias 或實際模型名稱尋找路由。
    
    查找優先順序：
    1. 完全匹配 alias
    2. 完全匹配 model_name
    3. 部分匹配 alias（大小寫不敏感）
    4. 部分匹配 model_name（路徑末段）
    """
    # 1. 完全匹配 alias
    if model in routes:
        return routes[model]
    
    # 2. 完全匹配 model_name
    for route in routes.values():
        if model == route.model_name:
            return route
    
    # 3. 大小寫不敏感匹配 alias
    model_lower = model.lower()
    for alias, route in routes.items():
        if model_lower == alias.lower():
            return route
    
    # 4. 部分匹配 model_name 的最後一段路徑名
    for route in routes.values():
        # 從 ./AImodels/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4 提取 NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4
        model_basename = route.model_name.rstrip("/").split("/")[-1]
        if model_lower == model_basename.lower():
            return route
        # 也檢查用戶輸入的是否是路徑
        user_basename = model.rstrip("/").split("/")[-1]
        if user_basename.lower() == model_basename.lower():
            return route
    
    return None


def get_available_models_help(routes: dict[str, GatewayRoute]) -> str:
    """生成可用模型的幫助訊息。"""
    lines = ["可用模型:"]
    for alias, route in sorted(routes.items()):
        model_basename = route.model_name.rstrip("/").split("/")[-1]
        lines.append(f"  • {alias} ({model_basename})")
    return "\n".join(lines)
