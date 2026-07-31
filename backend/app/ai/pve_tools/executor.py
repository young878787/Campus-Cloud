"""Validate and execute registry checks through the existing SSH transport."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import ValidationError
from sqlmodel import Session

from app.ai.pve_log.schemas import SSHExecRequest
from app.ai.pve_log.ssh_exec import ssh_exec
from app.ai.pve_tools.schemas import ResolvedProfile


async def execute_guest_check(
    args: dict[str, Any],
    *,
    profile: ResolvedProfile,
    session: Session | None,
    allowed_vmids: set[int] | None,
    requester_id: uuid.UUID | None,
    scope_type: str | None,
    scope_id: uuid.UUID | None,
) -> dict[str, Any]:
    try:
        vmid = int(args["vmid"])
        check_key = str(args["check_key"])
        raw_params = args["params"]
    except (KeyError, TypeError, ValueError) as exc:
        return {"status": "rejected", "error": f"缺少或無效的必填參數: {exc}"}

    if allowed_vmids is not None and vmid not in allowed_vmids:
        return {
            "check_key": check_key,
            "status": "rejected",
            "error": "目前只允許存取指定範圍內的 VM/LXC",
        }
    definition = next(
        (check for check in profile.checks if check.key == check_key),
        None,
    )
    if definition is None:
        return {
            "check_key": check_key,
            "status": "rejected",
            "error": "此 check 不存在或不屬於目前模板",
        }
    if definition.risk != "read_only":
        return {
            "check_key": check_key,
            "status": "rejected",
            "error": "此 check 不是可直接執行的唯讀檢查",
        }
    if not isinstance(raw_params, dict):
        return {
            "check_key": check_key,
            "status": "rejected",
            "error": "params 必須是物件",
        }
    try:
        params = definition.parameter_model.model_validate(raw_params)
    except ValidationError as exc:
        return {
            "check_key": check_key,
            "status": "rejected",
            "error": "params 驗證失敗",
            "details": exc.errors(include_url=False),
        }

    command = definition.command_builder(params)
    result = await ssh_exec(
        SSHExecRequest(
            vmid=vmid,
            command=command,
            ssh_user="root",
            require_confirm=False,
        ),
        session=session,
        allowed_vmids=allowed_vmids,
        requester_id=requester_id,
        scope_type=scope_type,
        scope_id=scope_id,
    )
    if result.blocked:
        return {
            "check_key": check_key,
            "status": "blocked",
            "summary": result.block_reason or "檢查被安全規則攔截",
            "exit_code": result.exit_code,
            "data": {},
            "stderr": result.stderr,
            "truncated": result.stdout_truncated or result.stderr_truncated,
        }
    if result.error:
        return {
            "check_key": check_key,
            "status": "failed",
            "summary": result.error,
            "exit_code": result.exit_code,
            "data": {},
            "stderr": result.stderr,
            "truncated": result.stdout_truncated or result.stderr_truncated,
        }
    summary, data = definition.result_parser(
        result.stdout,
        result.stderr,
        result.exit_code,
    )
    return {
        "check_key": check_key,
        "status": "passed" if result.exit_code == 0 else "failed",
        "summary": summary,
        "exit_code": result.exit_code,
        "data": data,
        "stderr": result.stderr,
        "truncated": result.stdout_truncated or result.stderr_truncated,
    }
