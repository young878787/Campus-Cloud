"""Python application runtime checks."""

from __future__ import annotations

from typing import Any

from app.ai.pve_tools.schemas import CheckDefinition, EmptyParams


def _text_parser(stdout: str, stderr: str, exit_code: int) -> tuple[str, dict[str, Any]]:
    value = stdout.strip()
    return (
        "檢查成功" if exit_code == 0 else "檢查失敗",
        {"value": value} if value else {"error_output": stderr.strip()},
    )


def _presence_parser(
    stdout: str, stderr: str, exit_code: int
) -> tuple[str, dict[str, Any]]:
    del stderr
    matched = exit_code == 0 and bool(stdout.strip())
    return (
        "偵測到 Python 應用程序" if matched else "未偵測到 Python 應用程序",
        {"matched": matched, "processes": stdout.splitlines() if matched else []},
    )


PYTHON_CHECKS = (
    CheckDefinition(
        key="python.version",
        label="Python 版本",
        description="讀取預設 python3 interpreter 版本",
        risk="read_only",
        parameter_model=EmptyParams,
        command_builder=lambda _params: "python3 --version",
        result_parser=_text_parser,
    ),
    CheckDefinition(
        key="python.environment",
        label="Python 環境邊界",
        description="辨識目前 interpreter、虛擬環境及可用套件管理工具",
        risk="read_only",
        parameter_model=EmptyParams,
        command_builder=lambda _params: (
            "python3 -c 'import os,sys; "
            'print("executable="+sys.executable); '
            'print("prefix="+sys.prefix); '
            'print("base_prefix="+sys.base_prefix); '
            'print("virtual_env="+os.environ.get("VIRTUAL_ENV",""))\''
            "; command -v uv || true; command -v poetry || true"
        ),
        result_parser=_text_parser,
    ),
    CheckDefinition(
        key="python.processes",
        label="Python 應用程序",
        description="搜尋 Python、Uvicorn、Gunicorn、Flask、Django 程序",
        risk="read_only",
        parameter_model=EmptyParams,
        command_builder=lambda _params: (
            "pgrep -a -f -- '[p]ython|[u]vicorn|[g]unicorn|[f]lask|[d]jango'"
        ),
        result_parser=_presence_parser,
    ),
    CheckDefinition(
        key="python.listening_ports",
        label="Python 監聽 Port",
        description="列出目前 TCP listening sockets，供對照 Python 程序",
        risk="read_only",
        parameter_model=EmptyParams,
        command_builder=lambda _params: "ss -lntp",
        result_parser=_text_parser,
    ),
)
