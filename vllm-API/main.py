#!/usr/bin/env python3
"""
快速啟動腳本 - 自動檢查和啟動 vLLM 服務
包含預啟動檢查、健康監控和錯誤診斷
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
import os
import shutil
import subprocess
import sys
import sysconfig
import time
from pathlib import Path
from urllib.request import urlopen

# 確保專案根目錄在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.multi_model import (
    build_gateway_routes,
    load_gateway_config,
    load_model_instances,
    validate_cluster_resources,
)
from config.settings import get_settings
from core.cluster import MultiModelEngineManager, StartupMode
from utils.health_utils import check_system_health
from utils.logging_utils import get_logger


@dataclass
class GatewayRuntime:
    """Gateway 子程序執行資訊。"""

    process: subprocess.Popen[bytes]
    host: str
    port: int
    log_path: Path


@dataclass
class ClusterRuntime:
    """集群與 Gateway 的整體執行資訊。"""

    manager: MultiModelEngineManager
    gateway: GatewayRuntime | None = None


def _resolve_python_bin(project_root: Path) -> str:
    """解析啟動子程序用的 Python 執行檔。"""
    venv_python = project_root / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _normalize_probe_host(host: str) -> str:
    """將 0.0.0.0/:: 轉為可探測地址。"""
    return "127.0.0.1" if host in {"0.0.0.0", "::"} else host


def _wait_gateway_ready(
    runtime: GatewayRuntime,
    timeout: int,
    logger,
) -> None:
    """等待 Gateway /health 就緒。"""
    probe_host = _normalize_probe_host(runtime.host)
    health_url = f"http://{probe_host}:{runtime.port}/health"
    start = time.time()

    while (time.time() - start) < timeout:
        process = runtime.process
        if process.poll() is not None:
            raise RuntimeError(
                f"Gateway 進程異常退出 (exit code: {process.returncode})，"
                f"請查看日誌: {runtime.log_path}"
            )

        try:
            with urlopen(health_url, timeout=2.0) as response:  # nosec B310 - 內部服務健康檢查
                if response.status == 200:
                    logger.success(f"Gateway 已就緒: {health_url}")
                    return
        except Exception:
            pass

        time.sleep(1)

    raise TimeoutError(
        f"等待 Gateway 就緒逾時 ({timeout}s): {health_url}，"
        f"請查看日誌: {runtime.log_path}"
    )


def _start_gateway_process(
    gateway_host: str,
    gateway_port: int,
    ready_timeout: int,
    logger,
) -> GatewayRuntime:
    """啟動 Gateway (uvicorn webapp.backend.main:app)。"""
    project_root = Path(__file__).resolve().parent
    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "cluster-gateway.log"

    python_bin = _resolve_python_bin(project_root)
    command = [
        python_bin,
        "-m",
        "uvicorn",
        "webapp.backend.main:app",
        "--host",
        gateway_host,
        "--port",
        str(gateway_port),
    ]

    with open(log_path, "w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            cwd=str(project_root),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
        )

    runtime = GatewayRuntime(
        process=process,
        host=gateway_host,
        port=gateway_port,
        log_path=log_path,
    )
    _wait_gateway_ready(runtime, timeout=ready_timeout, logger=logger)
    return runtime


def _stop_gateway_process(runtime: GatewayRuntime | None, logger) -> None:
    """停止 Gateway 子程序。"""
    if runtime is None:
        return

    process = runtime.process
    if process.poll() is not None:
        return

    logger.info("停止 Gateway 進程...")
    process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        logger.warning("Gateway 未在期限內關閉，改用 SIGKILL")
        process.kill()
        process.wait(timeout=5)


def pre_launch_check(settings=None, logger_name: str = "PreCheck") -> bool:
    """啟動前檢查"""
    logger = get_logger(logger_name)
    settings = settings or get_settings()
    settings.inject_env_vars()
    
    logger.section("啟動前檢查")

    # 依賴版本前置檢查（避免子進程才報 ImportError）
    if not check_dependency_compatibility(logger):
        return False

    if not check_runtime_cache_permissions(logger):
        return False

    if not check_native_build_toolchain(logger):
        return False
    
    # 檢查系統健康
    health = check_system_health()
    
    # 檢查 GPU
    if health.gpu_count == 0:
        logger.error("未檢測到 GPU，無法啟動 vLLM")
        logger.info("提示: 確保已安裝 CUDA 和 PyTorch GPU 版本")
        return False
    
    logger.success(f"檢測到 {health.gpu_count} 個 GPU")
    
    # 檢查 GPU 記憶體
    for i in range(health.gpu_count):
        total = health.gpu_memory_total_gb[i]
        used = health.gpu_memory_used_gb[i]
        available = total - used
        
        logger.info(f"GPU {i}: {available:.1f} GB 可用 / {total:.1f} GB 總計")
        
        if available < 10:
            logger.warning(f"GPU {i} 可用記憶體不足 10GB，可能無法載入大模型")
    
    # 檢查系統記憶體
    if health.memory_available_gb < 10:
        logger.warning(f"系統可用記憶體不足 10GB (當前: {health.memory_available_gb:.1f} GB)")
    else:
        logger.success(f"系統記憶體充足: {health.memory_available_gb:.1f} GB 可用")
    
    # 檢查模型路徑
    model_path = Path(settings.resolved_model_path)
    if model_path.exists():
        logger.success(f"模型已存在: {model_path}")
    else:
        if "/" in settings.model_name:
            logger.warning(f"模型不存在，將從 HuggingFace 下載: {settings.model_name}")
            if settings.hf_hub_offline == 1:
                logger.error("模型不存在且 HF_HUB_OFFLINE=1，無法下載")
                logger.info("解決方案: 設置 HF_HUB_OFFLINE=0 或手動下載模型")
                return False
        else:
            logger.error(f"模型路徑不存在: {settings.model_name}")
            return False
    
    # 檢查 CUDA 環境
    triton_ptxas = Path(settings.triton_ptxas_path)
    if not triton_ptxas.exists():
        logger.warning(f"Triton PTXAS 不存在: {triton_ptxas}")
        logger.info("對於 Blackwell 等新 GPU，建議檢查 CUDA 安裝")
    
    # 健康警告
    warnings = health.get_warnings()
    if warnings:
        logger.warning("系統健康警告:")
        for warning in warnings:
            logger.warning(f"  - {warning}")
    
    return True


def check_dependency_compatibility(logger) -> bool:
    """檢查關鍵 Python 套件版本相容性。"""
    try:
        hub_version = version("huggingface-hub")
    except PackageNotFoundError:
        logger.error("缺少 huggingface-hub 套件")
        logger.info("請執行: .venv/bin/pip install \"huggingface-hub>=0.34.0,<1.0\"")
        return False

    try:
        major = int(hub_version.split(".")[0])
    except Exception:
        logger.warning(f"無法解析 huggingface-hub 版本: {hub_version}")
        return True

    if major >= 1:
        logger.error(
            "huggingface-hub 版本不相容: "
            f"{hub_version}（當前 transformers 需要 < 1.0）"
        )
        logger.info("請執行: .venv/bin/pip install \"huggingface-hub>=0.34.0,<1.0\"")
        return False

    return True


def check_runtime_cache_permissions(logger) -> bool:
    """檢查 HF/Transformers runtime cache 目錄可寫性。"""
    cache_keys = [
        "HF_HUB_CACHE",
        "HUGGINGFACE_HUB_CACHE",
        "HF_HOME",
        "HF_MODULES_CACHE",
    ]
    for key in cache_keys:
        raw = os.environ.get(key)
        if not raw:
            continue
        path = Path(raw)
        try:
            path.mkdir(parents=True, exist_ok=True)
            test_file = path / ".write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink(missing_ok=True)
        except Exception as exc:
            logger.error(f"快取目錄不可寫: {key}={path}")
            logger.info(f"請修正目錄權限或改用可寫路徑，錯誤: {exc}")
            return False
    return True


def check_native_build_toolchain(logger) -> bool:
    """檢查 Triton 原生編譯依賴（gcc 與 Python.h）。"""
    gcc_path = shutil.which("gcc")
    if not gcc_path:
        logger.error("缺少 gcc，Triton 無法編譯 CUDA 驅動模組")
        logger.info("Ubuntu/Debian: sudo apt-get update && sudo apt-get install -y build-essential")
        return False

    include_dir_raw = sysconfig.get_paths().get("include", "")
    include_dir = Path(include_dir_raw) if include_dir_raw else None
    header_path = include_dir / "Python.h" if include_dir else None
    if header_path is None or not header_path.exists():
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        logger.error(
            "缺少 Python 開發標頭 Python.h，"
            "Triton 初始化會失敗（常見錯誤: fatal error: Python.h: No such file or directory）"
        )
        if header_path is not None:
            logger.info(f"預期標頭位置: {header_path}")
        logger.info(
            "Ubuntu/Debian: sudo apt-get update && "
            f"sudo apt-get install -y python{py_ver}-dev build-essential"
        )
        logger.info("若套件不存在，改用: sudo apt-get install -y python3-dev build-essential")
        return False

    return True


def quick_start_cluster(
    wait_ready: bool = True,
    timeout: int = 1800,
    base_env: str = ".env",
    gateway_env: str = ".env.gateway",
    skip_check: bool = False,
    startup_mode: StartupMode = StartupMode.SEQUENTIAL,
    startup_delay: float = 5.0,
    start_gateway: bool = True,
    gateway_ready_timeout: int = 60,
) -> ClusterRuntime | None:
    """一次啟動三模型集群。
    
    Args:
        wait_ready: 是否等待所有模型就緒
        timeout: 單個模型等待就緒的超時秒數
        base_env: 基礎設定檔路徑
        gateway_env: Gateway 設定檔路徑
        skip_check: 跳過預啟動檢查
        startup_mode: 啟動模式（SEQUENTIAL=串行, PARALLEL=並行）
        startup_delay: 串行模式下每個模型完成後的額外等待秒數
        start_gateway: 是否啟動 Gateway
        gateway_ready_timeout: Gateway 健康檢查超時秒數
    """
    logger = get_logger("ClusterLauncher")

    try:
        instances = load_model_instances(base_env_file=base_env, gateway_env_file=gateway_env)
        validate_cluster_resources(instances)
        gateway_config = load_gateway_config(gateway_env_file=gateway_env)
        routes = build_gateway_routes(instances)
    except Exception as exc:
        logger.error(f"載入集群設定失敗: {exc}")
        return None

    if not skip_check:
        logger.section("Cluster 預檢查")
        for instance in instances:
            logger.info(
                f"檢查 {instance.alias}: {instance.settings.model_name} "
                f"({instance.settings.api_host}:{instance.settings.api_port})"
            )
            ok = pre_launch_check(
                settings=instance.settings,
                logger_name=f"PreCheck:{instance.alias}",
            )
            if not ok:
                logger.error(f"模型 {instance.alias} 預檢查失敗，取消啟動")
                return None

    manager = MultiModelEngineManager(instances)
    gateway_runtime: GatewayRuntime | None = None
    try:
        logger.section("Cluster 啟動")
        manager.start_all(
            wait_ready=wait_ready,
            timeout=timeout,
            mode=startup_mode,
            startup_delay=startup_delay,
        )
        manager.print_status()

        logger.section("Gateway 路由")
        logger.info(f"Gateway: http://{gateway_config.host}:{gateway_config.port}")
        for alias, route in routes.items():
            logger.info(f"{alias} -> {route.base_url} (model={route.model_name})")

        if start_gateway:
            logger.section("Gateway 啟動")
            gateway_runtime = _start_gateway_process(
                gateway_host=gateway_config.host,
                gateway_port=gateway_config.port,
                ready_timeout=gateway_ready_timeout,
                logger=logger,
            )
            logger.info(
                f"Gateway 日誌: {gateway_runtime.log_path}"
            )
        else:
            logger.info("已跳過 Gateway 啟動 (--no-gateway)")

        logger.info("集群啟動完成，按 Ctrl+C 停止所有模型與 Gateway")
        return ClusterRuntime(manager=manager, gateway=gateway_runtime)
    except KeyboardInterrupt:
        logger.warning("集群啟動期間收到中斷信號，正在停止所有模型...")
        _stop_gateway_process(gateway_runtime, logger)
        manager.stop_all()
        raise
    except Exception as exc:
        logger.error(f"集群啟動失敗: {exc}")
        _stop_gateway_process(gateway_runtime, logger)
        manager.stop_all()
        return None


def main() -> None:
    """主函數"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="vLLM 集群啟動腳本（強制多模型共用模式）"
    )
    parser.add_argument(
        "--cluster",
        action="store_true",
        help="相容舊版旗標（已預設為集群模式，可省略）",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="不等待服務就緒（後台啟動）"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="等待服務就緒的超時時間（秒）"
    )
    parser.add_argument(
        "--skip-check",
        action="store_true",
        help="跳過預啟動檢查"
    )
    parser.add_argument(
        "--base-env",
        type=str,
        default=".env",
        help="集群共用設定檔路徑（預設 .env）"
    )
    parser.add_argument(
        "--gateway-env",
        type=str,
        default=".env.gateway",
        help="Gateway 設定檔路徑（預設 .env.gateway）"
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="使用並行啟動模式（不建議，較不穩定）。預設為串行模式：每個模型完全就緒後才啟動下一個"
    )
    parser.add_argument(
        "--startup-delay",
        type=float,
        default=5.0,
        help="串行模式下每個模型完成後的額外等待秒數（預設 5.0）"
    )
    parser.add_argument(
        "--no-gateway",
        action="store_true",
        help="只啟動模型，不啟動 Gateway"
    )
    parser.add_argument(
        "--gateway-ready-timeout",
        type=int,
        default=60,
        help="Gateway 健康檢查超時秒數（預設 60）"
    )
    args = parser.parse_args()
    
    logger = get_logger("Main")

    logger.info("已強制啟用多模型集群共用模式，不提供單模型回退路徑")
    logger.info(f"共用設定檔: {args.base_env}")
    logger.info(f"Gateway 設定檔: {args.gateway_env}")
    logger.info(f"啟動 Gateway: {'否' if args.no_gateway else '是'}")
    
    startup_mode = StartupMode.PARALLEL if args.parallel else StartupMode.SEQUENTIAL
    logger.info(f"啟動模式: {startup_mode.value}")

    try:
        runtime = quick_start_cluster(
            wait_ready=not args.no_wait,
            timeout=args.timeout,
            base_env=args.base_env,
            gateway_env=args.gateway_env,
            skip_check=args.skip_check,
            startup_mode=startup_mode,
            startup_delay=args.startup_delay,
            start_gateway=not args.no_gateway,
            gateway_ready_timeout=args.gateway_ready_timeout,
        )
    except KeyboardInterrupt:
        logger.info("收到中斷信號，啟動已取消")
        return
    
    if runtime is None:
        sys.exit(1)
    
    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        logger.info("收到中斷信號，正在停止集群與 Gateway...")
    finally:
        _stop_gateway_process(runtime.gateway, logger)
        runtime.manager.stop_all()


if __name__ == "__main__":
    main()
