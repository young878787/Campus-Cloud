"""執行環境設定檔的唯一讀寫邊界。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session, select

from app.models.execution_profile import ExecutionProfile, ExecutionProfileCommand
from app.models.resource import Resource
from app.schemas.execution_profile import ExecutionProfileContext

_LINUX_MARKERS = (
    "linux",
    "debian",
    "ubuntu",
    "alpine",
    "centos",
    "fedora",
    "rocky",
    "alma",
)


@dataclass(frozen=True)
class ResolvedResourceExecution:
    resource_type: str
    os_info: str
    execution_profile_id: uuid.UUID | None


def _normalize_resource_type(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"vm", "qemu"}:
        return "qemu"
    if normalized in {"lxc", "ct", "container"}:
        return "lxc"
    return "unknown"


def resolve_resource_execution(
    session: Session,
    *,
    resource_type: str | None,
    os_info: str | None,
    execution_profile_id: uuid.UUID | None,
    template_id: int | None,
    service_template_slug: str | None,
    batch_job_id: uuid.UUID | None,
    request_id: uuid.UUID | None,
) -> ResolvedResourceExecution:
    """Resolve creation-time system facts without guessing an OS version."""
    from app.models.batch_provision import BatchProvisionJob
    from app.models.vm_request import VMRequest
    from app.models.vm_template import VMTemplate

    resolved_type = _normalize_resource_type(resource_type)
    request = session.get(VMRequest, request_id) if request_id else None
    batch_job = session.get(BatchProvisionJob, batch_job_id) if batch_job_id else None
    if resolved_type == "unknown" and request is not None:
        resolved_type = _normalize_resource_type(request.resource_type)
    if resolved_type == "unknown" and batch_job is not None:
        resolved_type = _normalize_resource_type(batch_job.resource_type)
    if resolved_type == "unknown" and template_id is not None:
        resolved_type = "qemu"
    if resolved_type == "unknown" and service_template_slug:
        resolved_type = "lxc"

    profile: ExecutionProfile | None = None
    if execution_profile_id is not None:
        profile = session.get(ExecutionProfile, execution_profile_id)

    if profile is None and template_id is not None:
        vm_template = session.exec(
            select(VMTemplate).where(VMTemplate.pve_vmid == template_id)
        ).first()
        if vm_template and vm_template.execution_profile_id:
            profile = session.get(
                ExecutionProfile,
                vm_template.execution_profile_id,
            )

    candidate_text = " ".join(
        value
        for value in (
            os_info,
            service_template_slug,
            getattr(request, "os_info", None),
            getattr(request, "service_template_slug", None),
        )
        if value
    ).lower()
    if profile is None and candidate_text:
        profiles = list(
            session.exec(
                select(ExecutionProfile).where(
                    ExecutionProfile.enabled == True  # noqa: E712
                )
            ).all()
        )
        profile = next(
            (
                item
                for item in profiles
                if item.profile_key.lower() in candidate_text
                or item.system_name.lower() in candidate_text
            ),
            None,
        )
        if profile is None and any(marker in candidate_text for marker in _LINUX_MARKERS):
            profile = next(
                (item for item in profiles if item.profile_key == "linux"),
                None,
            )

    if profile is None:
        fallback_key = {
            "qemu": "vm-generic",
            "lxc": "lxc-generic",
            "unknown": "unknown-generic",
        }[resolved_type]
        profile = get_profile_by_key(session, fallback_key)

    resolved_os_info = str(os_info or "").strip()
    if not resolved_os_info and request is not None:
        resolved_os_info = str(request.os_info or "").strip()
    if not resolved_os_info and service_template_slug:
        resolved_os_info = service_template_slug
    if (
        not resolved_os_info
        and profile is not None
        and not profile.profile_key.endswith("-generic")
    ):
        version = f" {profile.system_version}" if profile.system_version else ""
        resolved_os_info = f"{profile.system_name}{version}".strip()
    if not resolved_os_info:
        resolved_os_info = {
            "qemu": "VM（作業系統未確認）",
            "lxc": "LXC（作業系統未確認）",
            "unknown": "受管資源（類型與作業系統未確認）",
        }[resolved_type]

    return ResolvedResourceExecution(
        resource_type=resolved_type,
        os_info=resolved_os_info,
        execution_profile_id=profile.id if profile else execution_profile_id,
    )


def reconcile_resource_execution_metadata(session: Session) -> dict[str, Any]:
    """Repair legacy/imported Resources using DB lineage, then PVE type."""
    from app.services.proxmox import proxmox_service

    resources = list(session.exec(select(Resource)).all())
    updated = 0
    unresolved = 0
    failed_vmids: list[int] = []
    for resource in resources:
        if (
            resource.resource_type in {"qemu", "lxc"}
            and resource.os_info
            and resource.execution_profile_id
        ):
            continue

        resource_type = resource.resource_type
        if resource_type not in {"qemu", "lxc"}:
            try:
                pve_resource = proxmox_service.find_resource(resource.vmid)
                resource_type = str(pve_resource.get("type") or "unknown")
            except Exception:
                failed_vmids.append(resource.vmid)

        execution = resolve_resource_execution(
            session,
            resource_type=resource_type,
            os_info=resource.os_info,
            execution_profile_id=resource.execution_profile_id,
            template_id=resource.template_id,
            service_template_slug=resource.service_template_slug,
            batch_job_id=resource.batch_job_id,
            request_id=resource.request_id,
        )
        changed = (
            resource.resource_type != execution.resource_type
            or resource.os_info != execution.os_info
            or resource.execution_profile_id != execution.execution_profile_id
        )
        resource.resource_type = execution.resource_type
        resource.os_info = execution.os_info
        resource.execution_profile_id = execution.execution_profile_id
        if changed:
            session.add(resource)
            updated += 1
        if (
            execution.resource_type == "unknown"
            or execution.execution_profile_id is None
        ):
            unresolved += 1
    session.commit()
    return {
        "scanned": len(resources),
        "updated": updated,
        "unresolved": unresolved,
        "failed_vmids": sorted(set(failed_vmids)),
    }


def get_profile_by_key(
    session: Session, profile_key: str, *, enabled_only: bool = True
) -> ExecutionProfile | None:
    statement = select(ExecutionProfile).where(
        ExecutionProfile.profile_key == profile_key
    )
    if enabled_only:
        statement = statement.where(ExecutionProfile.enabled == True)  # noqa: E712
    return session.exec(statement).first()


def get_resource_execution_profile(
    session: Session, vmid: int
) -> ExecutionProfileContext | None:
    statement = (
        select(ExecutionProfile)
        .join(Resource, Resource.execution_profile_id == ExecutionProfile.id)
        .where(Resource.vmid == vmid)
        .where(ExecutionProfile.enabled == True)  # noqa: E712
    )
    profile = session.exec(statement).first()
    if profile is None:
        return None
    return ExecutionProfileContext(
        profile_key=profile.profile_key,
        system_name=profile.system_name,
        system_version=profile.system_version,
        manual=profile.manual,
    )


def format_resource_execution_context(session: Session, vmid: int) -> str:
    """建立僅含已確認操作資料的 LLM context。"""
    statement = (
        select(ExecutionProfile)
        .join(Resource, Resource.execution_profile_id == ExecutionProfile.id)
        .where(Resource.vmid == vmid)
        .where(ExecutionProfile.enabled == True)  # noqa: E712
    )
    profile = session.exec(statement).first()
    if profile is None:
        return (
            f"VMID {vmid}：目前沒有已確認的系統手冊，"
            "請先使用通用唯讀查詢，或由管理者補齊模板設定。"
        )
    commands = get_enabled_profile_commands(session, profile.id)
    lines = [
        f"VMID {vmid} 已確認資料：",
        f"- 系統：{profile.system_name}",
        f"- 版本：{profile.system_version or '未確認'}",
        f"- 簡要手冊：{profile.manual}",
    ]
    if commands:
        lines.append("- 可用受管指令：")
        lines.extend(
            f"  - {command.command_key}: {command.command_template}"
            for command in commands
        )
    lines.append("以上內容不能略過權限、安全檢查或執行確認。")
    return "\n".join(lines)


def get_enabled_profile_commands(
    session: Session, profile_id: uuid.UUID
) -> list[ExecutionProfileCommand]:
    statement = (
        select(ExecutionProfileCommand)
        .where(ExecutionProfileCommand.profile_id == profile_id)
        .where(ExecutionProfileCommand.enabled == True)  # noqa: E712
        .order_by(
            ExecutionProfileCommand.category,
            ExecutionProfileCommand.command_key,
        )
    )
    return list(session.exec(statement).all())


def get_enabled_profile_commands_by_key(
    session: Session, profile_key: str
) -> list[ExecutionProfileCommand]:
    profile = get_profile_by_key(session, profile_key)
    return [] if profile is None else get_enabled_profile_commands(session, profile.id)


def format_profile_commands_for_prompt(
    commands: list[ExecutionProfileCommand],
) -> str:
    if not commands:
        return "目前沒有 template command catalog；請不要產生 check_steps。"
    return "\n".join(
        "\n".join(
            [
                f"- command_key: {command.command_key}",
                f"  command_label: {command.command_label}",
                f"  category: {command.category}",
                f"  description: {command.description}",
                f"  risk_level: {command.risk_level}",
                f"  requires_confirmation: {command.requires_confirmation}",
            ]
        )
        for command in commands
    )


def validate_profile_check_steps(
    profile_key: str,
    items: list[dict[str, Any]],
    commands: list[ExecutionProfileCommand],
) -> list[dict[str, Any]]:
    valid_commands = {command.command_key: command for command in commands}
    normalized_items: list[dict[str, Any]] = []
    for item in items:
        next_item = dict(item)
        valid_steps: list[dict[str, str]] = []
        raw_steps = item.get("check_steps")
        if isinstance(raw_steps, list):
            for raw_step in raw_steps:
                if not isinstance(raw_step, dict):
                    continue
                step_profile_key = str(
                    raw_step.get("template_key") or profile_key
                ).strip()
                command = valid_commands.get(str(raw_step.get("command_key") or "").strip())
                if step_profile_key != profile_key or command is None:
                    continue
                valid_steps.append(
                    {
                        "template_key": profile_key,
                        "command_key": command.command_key,
                        "command_label": command.command_label,
                    }
                )
        next_item["check_steps"] = valid_steps
        normalized_items.append(next_item)
    return normalized_items
