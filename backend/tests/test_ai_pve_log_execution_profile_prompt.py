import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.ai.pve_log import chat as chat_module
from app.models.execution_profile import ExecutionProfile
from app.models.resource import Resource


def _session_with_profile() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    profile = ExecutionProfile(
        profile_key="n8n",
        display_name="n8n",
        system_name="n8n",
        system_version="1.x",
        manual="n8n 由 systemd 管理。",
    )
    session.add(profile)
    session.flush()
    session.add(
        Resource(
            vmid=102,
            user_id=uuid.uuid4(),
            environment_type="n8n",
            execution_profile_id=profile.id,
            created_at=datetime.now(timezone.utc),
        )
    )
    session.commit()
    return session


@pytest.mark.asyncio
async def test_profile_context_is_rebuilt_when_frontend_sends_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    async def fake_completion(payload, timeout):
        captured.update(payload)
        return {"choices": [{"message": {"role": "assistant", "content": "n8n"}}]}

    monkeypatch.setattr(chat_module.vllm_client, "create_chat_completion", fake_completion)
    monkeypatch.setattr(
        chat_module,
        "settings",
        SimpleNamespace(
            VLLM_BASE_URL="http://test",
            VLLM_MODEL_NAME="test-model",
            VLLM_TIMEOUT=10,
        ),
    )

    response = await chat_module.chat(
        history=[
            {"role": "system", "content": "stale system context"},
            {"role": "user", "content": "幫我看下 VM102 的系統是什麼，不要使用 tools"},
        ],
        session=_session_with_profile(),
        allowed_vmids={102},
    )

    system_content = "\n".join(
        item["content"]
        for item in captured["messages"]
        if item["role"] == "system"
    )
    assert response.reply == "n8n"
    assert "VMID 102 已確認資料" in system_content
    assert "系統：n8n" in system_content
    assert "版本：1.x" in system_content
    assert "n8n 由 systemd 管理" in system_content
    assert "stale system context" not in system_content
    assert captured["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_profile_context_is_not_exposed_for_unauthorized_vmid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    async def fake_completion(payload, timeout):
        captured.update(payload)
        return {"choices": [{"message": {"role": "assistant", "content": "無權限"}}]}

    monkeypatch.setattr(chat_module.vllm_client, "create_chat_completion", fake_completion)
    monkeypatch.setattr(
        chat_module,
        "settings",
        SimpleNamespace(
            VLLM_BASE_URL="http://test",
            VLLM_MODEL_NAME="test-model",
            VLLM_TIMEOUT=10,
        ),
    )

    await chat_module.chat(
        message="VM102 是什麼系統",
        session=_session_with_profile(),
        allowed_vmids={103},
    )

    system_content = "\n".join(
        item["content"]
        for item in captured["messages"]
        if item["role"] == "system"
    )
    assert "系統：n8n" not in system_content
    assert "不在本次授權範圍" in system_content
