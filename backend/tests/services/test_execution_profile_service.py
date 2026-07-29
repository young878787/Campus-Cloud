import uuid
from datetime import datetime, timezone

from sqlmodel import Session, SQLModel, create_engine

from app.models.batch_provision import BatchProvisionJob
from app.models.execution_profile import ExecutionProfile, ExecutionProfileCommand
from app.models.resource import Resource
from app.repositories import resource as resource_repo
from app.services.execution_profile_service import (
    format_resource_execution_context,
    get_enabled_profile_commands_by_key,
    get_resource_execution_profile,
    reconcile_resource_execution_metadata,
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


def test_batch_lxc_without_template_gets_generic_profile_and_os_info() -> None:
    session = _session()
    lxc_profile = ExecutionProfile(
        profile_key="lxc-generic",
        display_name="Generic LXC",
        system_name="LXC",
        manual="LXC generic manual",
    )
    session.add(lxc_profile)
    session.flush()
    job = BatchProvisionJob(
        initiated_by=uuid.uuid4(),
        resource_type="lxc",
        hostname_prefix="lab",
        template_params="{}",
        created_at=datetime.now(timezone.utc),
    )
    session.add(job)
    session.flush()

    resource = resource_repo.create_resource(
        session=session,
        vmid=102,
        user_id=uuid.uuid4(),
        environment_type="批量建立",
        batch_job_id=job.id,
    )

    assert resource.resource_type == "lxc"
    assert resource.os_info == "LXC（作業系統未確認）"
    assert resource.execution_profile_id == lxc_profile.id
    assert resource.template_id is None
    prompt = format_resource_execution_context(session, 102)
    assert "系統：LXC" in prompt
    assert "LXC generic manual" in prompt


def test_lxc_ostemplate_maps_to_linux_profile() -> None:
    session = _session()
    linux_profile = ExecutionProfile(
        profile_key="linux",
        display_name="Linux",
        system_name="Linux",
        manual="Linux manual",
    )
    session.add(linux_profile)
    session.commit()

    resource = resource_repo.create_resource(
        session=session,
        vmid=103,
        user_id=uuid.uuid4(),
        resource_type="lxc",
        environment_type="自訂 LXC",
        os_info="local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst",
    )

    assert resource.resource_type == "lxc"
    assert resource.execution_profile_id == linux_profile.id
    assert resource.os_info.startswith("local:vztmpl/debian-12")


def test_service_slug_maps_to_specific_profile_before_generic_lxc() -> None:
    session = _session()
    profiles = [
        ExecutionProfile(
            profile_key="n8n",
            display_name="n8n",
            system_name="n8n",
            system_version="1.x",
            manual="n8n manual",
        ),
        ExecutionProfile(
            profile_key="lxc-generic",
            display_name="Generic LXC",
            system_name="LXC",
            manual="LXC manual",
        ),
    ]
    session.add_all(profiles)
    session.commit()

    resource = resource_repo.create_resource(
        session=session,
        vmid=104,
        user_id=uuid.uuid4(),
        resource_type="lxc",
        environment_type="服務模板",
        service_template_slug="n8n",
    )

    assert resource.execution_profile_id == profiles[0].id
    assert resource.os_info == "n8n"


def test_reconcile_uses_pve_type_for_legacy_resource_without_lineage(
    monkeypatch,
) -> None:
    session = _session()
    vm_profile = ExecutionProfile(
        profile_key="vm-generic",
        display_name="Generic VM",
        system_name="VM",
        manual="VM generic manual",
    )
    session.add(vm_profile)
    session.add(
        Resource(
            vmid=126,
            user_id=uuid.uuid4(),
            resource_type="unknown",
            environment_type="Custom",
            os_info=None,
            execution_profile_id=None,
            created_at=datetime.now(timezone.utc),
        )
    )
    session.commit()

    from app.services.proxmox import proxmox_service

    monkeypatch.setattr(
        proxmox_service,
        "find_resource",
        lambda vmid: {"vmid": vmid, "type": "qemu", "node": "pve"},
    )

    result = reconcile_resource_execution_metadata(session)
    resource = session.get(Resource, 126)

    assert result == {
        "scanned": 1,
        "updated": 1,
        "unresolved": 0,
        "failed_vmids": [],
    }
    assert resource is not None
    assert resource.resource_type == "qemu"
    assert resource.os_info == "VM（作業系統未確認）"
    assert resource.execution_profile_id == vm_profile.id
