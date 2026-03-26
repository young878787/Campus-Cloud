from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """配置應用程式的結構化日誌。"""
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # 設定基本配置
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # 設定第三方套件的日誌級別（避免過多輸出）
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
