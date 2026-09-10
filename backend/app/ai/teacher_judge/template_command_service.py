"""Template command catalog helpers for Teacher Judge rubric analysis."""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.models.teacher_judge_template_command import TeacherJudgeTemplateCommand

SUPPORTED_TEMPLATE_KEYS = {"linux", "python", "n8n", "postgresql"}
DEFAULT_SYSTEM_COMMAND_TIMEOUT_SECONDS = 30

GENERAL_COMMAND = TeacherJudgeTemplateCommand(
    template_key="linux",
    command_key="system.run_command",
    command_label="通用受控指令",
    category="inspection",
    command_template="argv + cwd + timeout",
    description=(
        "平台已登錄的通用能力，可在指定工作目錄以 argv list 與有限 timeout "
        "執行單一唯讀／診斷指令，"
        "適用所有通過平台政策的唯讀／診斷系統指令；cat、pwd、echo、"
        "唯讀 git 子命令、有限次數 ping 等只是一部分範例，"
        "並原樣收集 exit code、stdout、stderr。cd 請以 cwd 表示；"
        "不得使用 shell、pipe、redirect、寫入、安裝、修復或破壞性操作。"
        "命令會立即執行；平台自動套用安全逾時上限，不需要老師指定等待時間。"
        "requires_confirmation 只是未來執行核准，不是要求老師新增權限。"
    ),
    risk_level="executes_command",
    requires_confirmation=True,
)


def get_enabled_template_commands(
    session: Session,
    template_key: str,
    *,
    include_cross_template: bool = False,
) -> list[TeacherJudgeTemplateCommand]:
    """Return enabled commands, optionally including controlled cross-template capabilities."""
    statement = (
        select(TeacherJudgeTemplateCommand)
        .where(TeacherJudgeTemplateCommand.enabled == True)  # noqa: E712
        .order_by(
            TeacherJudgeTemplateCommand.template_key,
            TeacherJudgeTemplateCommand.category,
            TeacherJudgeTemplateCommand.command_key,
        )
    )
    if not include_cross_template:
        statement = statement.where(
            TeacherJudgeTemplateCommand.template_key == template_key
        )
    commands = list(session.exec(statement).all())
    if include_cross_template:
        if not any(
            command.command_key == GENERAL_COMMAND.command_key for command in commands
        ):
            commands.append(GENERAL_COMMAND)
        commands.sort(
            key=lambda command: (
                command.template_key != template_key,
                command.template_key,
                command.category,
                command.command_key,
            )
        )
    return commands


def format_template_commands_for_prompt(
    commands: list[TeacherJudgeTemplateCommand],
) -> str:
    """Format enabled commands for LLM prompt injection."""
    if not commands:
        return "目前沒有 template command catalog；請不要產生 check_steps。"

    lines = []
    for command in commands:
        lines.append(
            "\n".join(
                [
                    f"- template_key: {command.template_key}",
                    f"  command_key: {command.command_key}",
                    f"  command_label: {command.command_label}",
                    f"  category: {command.category}",
                    f"  description: {command.description}",
                    f"  risk_level: {command.risk_level}",
                    f"  requires_confirmation: {command.requires_confirmation}",
                ]
            )
        )
    return "\n".join(lines)


def validate_check_steps(
    template_key: str,
    items: list[dict[str, Any]],
    commands: list[TeacherJudgeTemplateCommand],
) -> list[dict[str, Any]]:
    """
    Keep only check steps that reference enabled commands for the selected template.

    This helper accepts item-shaped dictionaries so tests and callers can validate
    raw LLM payloads without needing to instantiate Pydantic schemas first.
    """
    valid_commands = {
        (command.template_key, command.command_key): command for command in commands
    }
    normalized_items: list[dict[str, Any]] = []
    for item in items:
        next_item = dict(item)
        valid_steps: list[dict[str, Any]] = []
        raw_steps = item.get("check_steps")
        if isinstance(raw_steps, list):
            for raw_step in raw_steps:
                if not isinstance(raw_step, dict):
                    continue
                step_template_key = str(raw_step.get("template_key") or template_key).strip()
                command_key = str(raw_step.get("command_key") or "").strip()
                command = valid_commands.get((step_template_key, command_key))
                if command is None:
                    continue
                step = {
                    "template_key": command.template_key,
                    "command_key": command.command_key,
                    "command_label": command.command_label,
                }
                raw_parameters = raw_step.get("parameters")
                if isinstance(raw_parameters, dict) or (
                    command.command_key == "system.run_command"
                ):
                    parameters = (
                        dict(raw_parameters) if isinstance(raw_parameters, dict) else {}
                    )
                    timeout = parameters.get("timeout_seconds")
                    if command.command_key == "system.run_command" and (
                        not isinstance(timeout, int)
                        or isinstance(timeout, bool)
                        or not 1 <= timeout <= 300
                    ):
                        parameters["timeout_seconds"] = (
                            DEFAULT_SYSTEM_COMMAND_TIMEOUT_SECONDS
                        )
                    step["parameters"] = parameters
                valid_steps.append(step)
        next_item["check_steps"] = valid_steps
        normalized_items.append(next_item)
    return normalized_items


__all__ = [
    "DEFAULT_SYSTEM_COMMAND_TIMEOUT_SECONDS",
    "GENERAL_COMMAND",
    "SUPPORTED_TEMPLATE_KEYS",
    "format_template_commands_for_prompt",
    "get_enabled_template_commands",
    "validate_check_steps",
]
