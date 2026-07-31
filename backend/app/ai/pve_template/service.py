"""Orchestration for the isolated AI PVE template test feature."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session

from app.ai.pve_log.chat import chat as pve_chat
from app.ai.pve_log.schemas import ChatResponse, SSHExecResult
from app.ai.pve_log.ssh_exec import (
    confirm_exec,
    peek_pending_request,
    peek_pending_scope,
)
from app.ai.pve_template.prompts import compose_system_prompt
from app.ai.pve_template.repository import (
    get_by_id,
    get_by_key,
)
from app.ai.pve_template.repository import (
    list_enabled as list_enabled_templates,
)
from app.ai.pve_template.schemas import (
    AIPVETemplateChatRequest,
    AIPVETemplateChatResponse,
    AIPVETemplateRead,
    AIPVETemplateSSHConfirmRequest,
)
from app.core.authorizers import require_resource_access
from app.exceptions import BadRequestError, NotFoundError
from app.repositories import resource as resource_repo

_PENDING_CONTEXT_TTL = 300


@dataclass(slots=True)
class _PendingContext:
    created_at: float
    vmid: int
    messages: list[dict[str, Any]]


_pending_context: dict[str, _PendingContext] = {}


def _cleanup_pending_context() -> None:
    now = time.monotonic()
    for token, context in list(_pending_context.items()):
        if now - context.created_at > _PENDING_CONTEXT_TTL:
            _pending_context.pop(token, None)


def _authorize_vmid(*, session: Session, current_user: Any, vmid: int) -> Any:
    resource = resource_repo.get_resource_by_vmid(session=session, vmid=vmid)
    if resource is None:
        raise NotFoundError(f"VMID={vmid} 未在測試後端登記")
    require_resource_access(
        current_user,
        resource.user_id,
        detail="目前使用者沒有此測試 VMID 的存取權限",
    )
    return resource


def list_templates(*, session: Session) -> list[AIPVETemplateRead]:
    return [
        AIPVETemplateRead.model_validate(item, from_attributes=True)
        for item in list_enabled_templates(session=session)
    ]


def _response(
    *,
    template_key: str,
    vmid: int,
    response: ChatResponse,
    confirmation_result: SSHExecResult | None = None,
) -> AIPVETemplateChatResponse:
    return AIPVETemplateChatResponse(
        template_key=template_key,
        vmid=vmid,
        reply=response.reply,
        tools_called=response.tools_called,
        needs_confirmation=response.needs_confirmation,
        messages=response.messages,
        error=response.error,
        confirmation_result=confirmation_result,
    )


def _remember_pending(*, vmid: int, response: ChatResponse) -> None:
    _cleanup_pending_context()
    for record in response.tools_called:
        result = record.result or {}
        token = result.get("confirm_token")
        if token and result.get("pending"):
            _pending_context[str(token)] = _PendingContext(
                created_at=time.monotonic(),
                vmid=vmid,
                messages=[dict(message) for message in response.messages],
            )


async def chat(
    *, request: AIPVETemplateChatRequest, current_user: Any, session: Session
) -> AIPVETemplateChatResponse:
    template = get_by_key(session=session, template_key=request.template_key)
    if template is None or not template.enabled:
        raise NotFoundError("找不到可用的 AI PVE template")
    _authorize_vmid(session=session, current_user=current_user, vmid=request.vmid)

    response = await pve_chat(
        message=request.message,
        history=request.messages,
        session=session,
        allowed_vmids={request.vmid},
        requester_id=current_user.id,
        scope_type="template",
        scope_id=template.id,
        system_prompt=compose_system_prompt(template, vmid=request.vmid),
        template_key=template.template_key,
    )
    _remember_pending(vmid=request.vmid, response=response)
    return _response(template_key=template.template_key, vmid=request.vmid, response=response)


def _replace_pending_tool_result(
    messages: list[dict[str, Any]],
    result: SSHExecResult,
    *,
    approved: bool,
) -> list[dict[str, Any]]:
    replaced = [dict(message) for message in messages]
    for message in reversed(replaced):
        if message.get("role") != "tool":
            continue
        try:
            content = json.loads(str(message.get("content", "")))
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(content, dict) and content.get("pending"):
            resumed_result = result.model_dump(mode="json")
            resumed_result["confirmation_decision"] = (
                "approved" if approved else "rejected"
            )
            message["content"] = json.dumps(
                resumed_result,
                ensure_ascii=False,
            )
            break
    return replaced


async def confirm_ssh(
    *,
    request: AIPVETemplateSSHConfirmRequest,
    current_user: Any,
    session: Session,
) -> AIPVETemplateChatResponse:
    token = request.token or request.confirm_token or ""
    pending_request = peek_pending_request(token)
    scope_type, scope_id = peek_pending_scope(token)
    if pending_request is None or scope_type != "template" or scope_id is None:
        raise BadRequestError("確認 token 無效、已過期或不是 AI PVE template 請求")

    template = get_by_id(session=session, template_id=scope_id)
    if template is None or not template.enabled:
        raise NotFoundError("此 AI PVE template 已不存在或停用")
    _authorize_vmid(session=session, current_user=current_user, vmid=pending_request.vmid)

    result = await confirm_exec(
        request,
        session=session,
        requester_id=current_user.id,
        scope_type="template",
        scope_id=scope_id,
        allowed_vmids={pending_request.vmid},
    )
    _cleanup_pending_context()
    # Token still exists means confirm_exec rejected the caller/scope before
    # consuming it. Keep both stores intact so the legitimate owner can retry.
    if peek_pending_request(token) is not None:
        return AIPVETemplateChatResponse(
            template_key=template.template_key,
            vmid=pending_request.vmid,
            reply="確認未生效，原指令仍在等待有效的使用者決策。",
            error=result.error or result.block_reason,
            confirmation_result=result,
        )

    context = _pending_context.pop(token, None)
    if context is None or result.pending:
        return AIPVETemplateChatResponse(
            template_key=template.template_key,
            vmid=pending_request.vmid,
            reply="找不到可恢復的 AI 對話內容，請重新發起任務。",
            error=result.error or result.block_reason or "AI 對話接續內容已過期",
            confirmation_result=result,
        )

    resumed = await pve_chat(
        history=_replace_pending_tool_result(
            context.messages,
            result,
            approved=request.approved,
        ),
        session=session,
        allowed_vmids={context.vmid},
        requester_id=current_user.id,
        scope_type="template",
        scope_id=template.id,
        system_prompt=compose_system_prompt(template, vmid=context.vmid),
        template_key=template.template_key,
    )
    _remember_pending(vmid=context.vmid, response=resumed)
    return _response(
        template_key=template.template_key,
        vmid=context.vmid,
        response=resumed,
        confirmation_result=result,
    )


__all__ = ["chat", "confirm_ssh", "list_templates"]
