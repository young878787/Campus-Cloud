#!/usr/bin/env python3
"""
快速啟動腳本 - 自動檢查和啟動 vLLM 服務
包含預啟動檢查、健康監控和錯誤診斷
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# 確保專案根目錄在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import get_settings
from core.engine import VLLMEngine
from utils.health_utils import check_system_health
from utils.logging_utils import get_logger


def pre_launch_check() -> bool:
    """啟動前檢查"""
    logger = get_logger("PreCheck")
    settings = get_settings()
    
    logger.section("啟動前檢查")
    
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


def quick_start(wait_ready: bool = True, timeout: int = 600) -> VLLMEngine | None:
    """快速啟動 vLLM 服務"""
    logger = get_logger("Launcher")
    
    # 預啟動檢查
    if not pre_launch_check():
        logger.error("預啟動檢查失敗，取消啟動")
        logger.info("運行 'python 診斷工具.py' 查看詳細診斷資訊")
        return None
    
    # 啟動引擎
    logger.section("啟動 vLLM 服務")
    engine = VLLMEngine()
    
    try:
        engine.start(wait_ready=wait_ready, timeout=timeout)
        engine.print_status()
        
        # 啟動後健康檢查
        logger.section("啟動後健康檢查")
        health = check_system_health()
        
        for i in range(health.gpu_count):
            used = health.gpu_memory_used_gb[i]
            total = health.gpu_memory_total_gb[i]
            usage_percent = (used / total * 100) if total > 0 else 0
            logger.info(f"GPU {i} 記憶體使用: {used:.1f}/{total:.1f} GB ({usage_percent:.1f}%)")
        
        logger.success("vLLM 服務啟動成功！")
        logger.info(f"API 地址: {engine.base_url}")
        logger.info("按 Ctrl+C 停止服務")
        
        return engine
        
    except Exception as e:
        logger.error(f"啟動失敗: {e}")
        logger.info("運行 'python 診斷工具.py' 查看詳細診斷資訊")
        return None


def main() -> None:
    """主函數"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="vLLM 快速啟動腳本 - 帶預檢查和健康監控"
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="不等待服務就緒（後台啟動）"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="等待服務就緒的超時時間（秒）"
    )
    parser.add_argument(
        "--skip-check",
        action="store_true",
        help="跳過預啟動檢查"
    )
    
    args = parser.parse_args()
    
    logger = get_logger("Main")
    
    # 跳過檢查直接啟動
    if args.skip_check:
        logger.warning("已跳過預啟動檢查")
        engine = VLLMEngine()
        try:
            engine.start(wait_ready=not args.no_wait, timeout=args.timeout)
            if not args.no_wait:
                engine.print_status()
                logger.info("按 Ctrl+C 停止服務")
                engine._process.wait() if engine._process else None
        except KeyboardInterrupt:
            logger.info("收到中斷信號")
        finally:
            engine.stop()
        return
    
    # 正常啟動流程
    engine = quick_start(wait_ready=not args.no_wait, timeout=args.timeout)
    
    if engine is None:
        sys.exit(1)
    
    # 保持運行
    try:
        if engine._process:
            engine._process.wait()
    except KeyboardInterrupt:
        logger.info("收到中斷信號")
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
