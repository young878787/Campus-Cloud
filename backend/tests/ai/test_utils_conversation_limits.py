"""app/ai/utils.py 的 AI 對話長度上限：訊息數或總字數超過上限時拒絕，正常長度的對話放行。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ai.utils import (
    MAX_CONVERSATION_CHARS,
    MAX_CONVERSATION_MESSAGES,
    ensure_conversation_within_limits,
)
from app.exceptions import BadRequestError

# ── 4. AI 對話長度上限 ──────────────────────────────────────────────────────


def test_conversation_message_count_is_capped() -> None:
    messages = [SimpleNamespace(content="hi")] * (MAX_CONVERSATION_MESSAGES + 1)
    with pytest.raises(BadRequestError):
        ensure_conversation_within_limits(messages)


def test_conversation_total_length_is_capped() -> None:
    messages = [SimpleNamespace(content="x" * (MAX_CONVERSATION_CHARS + 1))]
    with pytest.raises(BadRequestError):
        ensure_conversation_within_limits(messages)


def test_normal_conversation_passes() -> None:
    ensure_conversation_within_limits([SimpleNamespace(content="請幫我選範本")])
