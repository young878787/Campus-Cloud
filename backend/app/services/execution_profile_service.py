"""執行環境設定檔的唯一讀寫邊界。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlmodel import Session, select

from app.models.execution_profile import ExecutionProfile, ExecutionProfileCommand
from app.models.resource import Resource
from app.schemas.execution_profile import ExecutionProfileContext


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
