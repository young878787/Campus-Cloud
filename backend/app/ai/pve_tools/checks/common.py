"""Checks reusable by more than one machine role."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.ai.pve_tools.schemas import CheckDefinition, EmptyParams


class ProcessSearchParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selector: Literal["n8n"]


def _status_summary(stdout: str, stderr: str, exit_code: int) -> tuple[str, dict[str, Any]]:
    del stderr
    return (
        "檢查成功" if exit_code == 0 else "檢查未通過",
        {"matched": exit_code == 0 and bool(stdout.strip())},
    )


def _disk_parser(stdout: str, stderr: str, exit_code: int) -> tuple[str, dict[str, Any]]:
    del stderr
    lines = [line for line in stdout.splitlines() if line.strip()]
    return (
        "已取得磁碟使用量" if exit_code == 0 else "無法取得磁碟使用量",
        {"filesystems": lines[1:]} if exit_code == 0 else {},
    )


def _process_command(params: BaseModel) -> str:
    if not isinstance(params, ProcessSearchParams):
        raise TypeError("service.process_search received invalid params")
    return "pgrep -a -f -- '[n]8n'"


COMMON_CHECKS = (
    CheckDefinition(
        key="system.disk_usage",
        label="磁碟使用量",
        description="檢查 guest 檔案系統容量與使用率",
        risk="read_only",
        parameter_model=EmptyParams,
        command_builder=lambda _params: "df -P -h",
        result_parser=_disk_parser,
    ),
    CheckDefinition(
        key="service.process_search",
        label="服務程序搜尋",
        description="搜尋受控服務的執行程序；params.selector 目前僅允許 n8n",
        risk="read_only",
        parameter_model=ProcessSearchParams,
        command_builder=_process_command,
        result_parser=_status_summary,
    ),
)
