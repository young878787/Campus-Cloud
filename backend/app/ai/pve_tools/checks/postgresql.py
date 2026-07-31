"""Credential-free PostgreSQL health checks."""

from __future__ import annotations

from typing import Any

from app.ai.pve_tools.schemas import CheckDefinition, EmptyParams


def _text_parser(stdout: str, stderr: str, exit_code: int) -> tuple[str, dict[str, Any]]:
    value = stdout.strip()
    return (
        "檢查成功" if exit_code == 0 else "檢查失敗",
        {"value": value} if value else {"error_output": stderr.strip()},
    )


def _readiness_parser(
    stdout: str, stderr: str, exit_code: int
) -> tuple[str, dict[str, Any]]:
    message = (stdout or stderr).strip()
    ready = exit_code == 0
    return (
        "PostgreSQL 已可接受連線" if ready else "PostgreSQL 尚未可接受連線",
        {"ready": ready, "message": message},
    )


def _port_parser(stdout: str, stderr: str, exit_code: int) -> tuple[str, dict[str, Any]]:
    del stderr
    listening = exit_code == 0 and bool(stdout.strip())
    return (
        "PostgreSQL port 5432 正在監聽"
        if listening
        else "未偵測到 PostgreSQL port 5432",
        {"listening": listening, "port": 5432},
    )


POSTGRESQL_CHECKS = (
    CheckDefinition(
        key="postgresql.version",
        label="PostgreSQL Client 版本",
        description="讀取本機 psql client 版本，不連線或查詢資料庫",
        risk="read_only",
        parameter_model=EmptyParams,
        command_builder=lambda _params: "psql --version",
        result_parser=_text_parser,
    ),
    CheckDefinition(
        key="postgresql.readiness",
        label="PostgreSQL Readiness",
        description="以 pg_isready 檢查本機 PostgreSQL 是否接受連線，不傳送 credential",
        risk="read_only",
        parameter_model=EmptyParams,
        command_builder=lambda _params: "pg_isready --timeout=5",
        result_parser=_readiness_parser,
    ),
    CheckDefinition(
        key="postgresql.service_status",
        label="PostgreSQL 服務狀態",
        description="讀取 systemd PostgreSQL service 狀態，不進行啟停操作",
        risk="read_only",
        parameter_model=EmptyParams,
        command_builder=lambda _params: (
            "systemctl status postgresql --no-pager --lines=20"
        ),
        result_parser=_text_parser,
    ),
    CheckDefinition(
        key="postgresql.port_5432",
        label="PostgreSQL 監聽 Port",
        description="檢查 PostgreSQL 預設 port 5432 是否監聽",
        risk="read_only",
        parameter_model=EmptyParams,
        command_builder=lambda _params: (
            "ss -lntp | grep -E '(^|[.:])5432([[:space:]]|$)'"
        ),
        result_parser=_port_parser,
    ),
)
