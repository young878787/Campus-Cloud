"""N8N-specific deterministic checks."""

from __future__ import annotations

from typing import Any

from app.ai.pve_tools.schemas import CheckDefinition, EmptyParams


def _port_parser(stdout: str, stderr: str, exit_code: int) -> tuple[str, dict[str, Any]]:
    del stderr
    listening = exit_code == 0 and bool(stdout.strip())
    return (
        "n8n port 5678 正在監聽" if listening else "未偵測到 n8n port 5678",
        {"listening": listening, "port": 5678},
    )


def _http_parser(stdout: str, stderr: str, exit_code: int) -> tuple[str, dict[str, Any]]:
    del stderr
    raw_status = stdout.strip()
    http_status = int(raw_status) if raw_status.isdigit() else None
    ready = exit_code == 0 and http_status is not None and 200 <= http_status < 500
    return (
        f"localhost:5678 回傳 HTTP {http_status}"
        if http_status is not None
        else "無法取得 localhost:5678 HTTP 狀態",
        {"http_status": http_status, "ready": ready},
    )


N8N_CHECKS = (
    CheckDefinition(
        key="n8n.port_5678",
        label="N8N 監聽 Port",
        description="檢查 n8n 預設 port 5678 是否監聽",
        risk="read_only",
        parameter_model=EmptyParams,
        command_builder=lambda _params: (
            "ss -lntp | grep -E '(^|[.:])5678([[:space:]]|$)'"
        ),
        result_parser=_port_parser,
    ),
    CheckDefinition(
        key="n8n.local_http",
        label="N8N 本機 HTTP",
        description="檢查 localhost n8n HTTP readiness",
        risk="read_only",
        parameter_model=EmptyParams,
        command_builder=lambda _params: (
            "curl --silent --show-error --output /dev/null "
            "--write-out '%{http_code}' --max-time 5 http://127.0.0.1:5678"
        ),
        result_parser=_http_parser,
    ),
)
