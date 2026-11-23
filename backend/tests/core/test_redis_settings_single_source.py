"""app/features/ai/config.py 的 Redis 設定必須與 app/core/config.py 共用同一來源，不得各自讀取。"""

from __future__ import annotations


def test_redis_settings_have_a_single_source() -> None:
    from app.core.config import settings as core_settings
    from app.features.ai.config import settings as ai_settings

    assert ai_settings.redis_enabled is core_settings.REDIS_ENABLED
    assert ai_settings.redis_url == core_settings.REDIS_URL
