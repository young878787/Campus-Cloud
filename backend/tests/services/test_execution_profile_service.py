import uuid
from datetime import datetime, timezone

from sqlmodel import Session, SQLModel, create_engine

from app.models.execution_profile import ExecutionProfile, ExecutionProfileCommand
from app.models.resource import Resource
from app.services.execution_profile_service import (
    format_resource_execution_context,
    get_enabled_profile_commands_by_key,
    get_resource_execution_profile,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_resource_context_is_whitelisted_and_filters_disabled_commands() -> None:
    session = _session()
    profile = ExecutionProfile(
        profile_key="n8n-1.x",
        display_name="n8n 1.x",
        system_name="n8n",
        system_version="1.x",
        manual="以 systemd 查詢服務狀態。",
    )
    session.add(profile)
    session.flush()
    session.add_all(
        [
            ExecutionProfileCommand(
                profile_id=profile.id,
                command_key="service.status",
                command_label="服務狀態",
                category="service",
                command_template="systemctl status n8n",
                description="唯讀服務狀態",
            ),
            ExecutionProfileCommand(
                profile_id=profile.id,
                command_key="service.restart",
                command_label="重新啟動",
                category="service",
                command_template="systemctl restart n8n",
                description="重新啟動服務",
                enabled=False,
            ),
        ]
    )
    session.add(
        Resource(
            vmid=157,
            user_id=uuid.uuid4(),
            environment_type="n8n",
            execution_profile_id=profile.id,
            ssh_private_key_encrypted="must-not-leak",
            created_at=datetime.now(timezone.utc),
        )
    )
    session.commit()

    context = get_resource_execution_profile(session, 157)
    assert context is not None
    assert context.model_dump() == {
        "profile_key": "n8n-1.x",
        "system_name": "n8n",
        "system_version": "1.x",
        "manual": "以 systemd 查詢服務狀態。",
    }
    prompt = format_resource_execution_context(session, 157)
    assert "systemctl status n8n" in prompt
    assert "systemctl restart n8n" not in prompt
    assert "must-not-leak" not in prompt


def test_disabled_profile_is_not_available() -> None:
    session = _session()
    profile = ExecutionProfile(
        profile_key="disabled",
        display_name="Disabled",
        system_name="Linux",
        manual="disabled",
        enabled=False,
    )
    session.add(profile)
    session.flush()
    session.add(
        Resource(
            vmid=999,
            user_id=uuid.uuid4(),
            environment_type="Linux",
            execution_profile_id=profile.id,
            created_at=datetime.now(timezone.utc),
        )
    )
    session.commit()

    assert get_resource_execution_profile(session, 999) is None
    assert get_enabled_profile_commands_by_key(session, "disabled") == []
    assert "目前沒有已確認的系統手冊" in format_resource_execution_context(
        session, 999
    )
