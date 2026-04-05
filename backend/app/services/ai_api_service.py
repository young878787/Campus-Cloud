import json
import logging
import secrets
import time
import uuid
from datetime import datetime, timedelta
from typing import AsyncGenerator

import httpx
from sqlmodel import Session, select

from app.ai_api.config import settings as ai_api_settings
from app.core.security import decrypt_value, encrypt_value
from app.exceptions import BadRequestError, NotFoundError, PermissionDeniedError
from app.models import (
    AIAPICredential,
    AIAPIRequest,
    AIAPIRequestStatus,
    AIAPIUsage,
    User,
    get_datetime_utc,
)
from app.schemas import (
    AIAPICredentialPublic,
    AIAPICredentialsPublic,
    AIAPIRequestCreate,
    AIAPIRequestPublic,
    AIAPIRequestReview,
    AIAPIRequestsPublic,
    Message,
)
from app.services import audit_service

logger = logging.getLogger(__name__)

DEFAULT_REQUEST_RATE_LIMIT = 20


def _generate_user_api_key() -> str:
    return f"ccai_{secrets.token_urlsafe(24)}"


def _credential_prefix(api_key: str) -> str:
    api_key = api_key.strip()
    return api_key[: min(8, len(api_key))]


def _get_owned_credential(
    *, session: Session, credential_id: uuid.UUID, current_user
) -> AIAPICredential:
    credential = session.get(AIAPICredential, credential_id)
    if not credential:
        raise NotFoundError("AI API credential not found")
    if not current_user.is_superuser and credential.user_id != current_user.id:
        raise PermissionDeniedError("Not enough privileges")
    return credential


def _to_request_public(req: AIAPIRequest) -> AIAPIRequestPublic:
    return AIAPIRequestPublic(
        id=req.id,
        user_id=req.user_id,
        user_email=req.user.email if req.user else None,
        user_full_name=req.user.full_name if req.user else None,
        purpose=req.purpose,
        api_key_name=req.api_key_name,
        duration=req.duration,
        rate_limit=req.rate_limit,
        status=req.status,
        reviewer_id=req.reviewer_id,
        reviewer_email=req.reviewer.email if req.reviewer else None,
        review_comment=req.review_comment,
        reviewed_at=req.reviewed_at,
        created_at=req.created_at,
    )


def _to_credential_public(credential: AIAPICredential) -> AIAPICredentialPublic:
    return AIAPICredentialPublic(
        id=credential.id,
        request_id=credential.request_id,
        base_url=credential.base_url,
        api_key=decrypt_value(credential.api_key_encrypted),
        api_key_prefix=credential.api_key_prefix,
        api_key_name=credential.api_key_name,
        rate_limit=credential.rate_limit,
        expires_at=credential.expires_at,
        revoked_at=credential.revoked_at,
        created_at=credential.created_at,
    )


def create_request(
    *, session: Session, request_in: AIAPIRequestCreate, user
) -> AIAPIRequestPublic:
    db_request = AIAPIRequest(
        user_id=user.id,
        purpose=request_in.purpose.strip(),
        api_key_name=request_in.api_key_name.strip(),
        duration=request_in.duration,
        rate_limit=DEFAULT_REQUEST_RATE_LIMIT,
    )
    session.add(db_request)
    audit_service.log_action(
        session=session,
        user_id=user.id,
        action="ai_api_request_submit",
        details=f"Submitted AI API request. Purpose: {db_request.purpose}",
        commit=False,
    )
    session.commit()
    session.refresh(db_request)
    logger.info("User %s submitted AI API request %s", user.email, db_request.id)
    return _to_request_public(db_request)


def list_requests_by_user(
    *, session: Session, user_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> AIAPIRequestsPublic:
    count_query = select(AIAPIRequest.id).where(AIAPIRequest.user_id == user_id)
    data_query = (
        select(AIAPIRequest)
        .where(AIAPIRequest.user_id == user_id)
        .order_by(AIAPIRequest.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return AIAPIRequestsPublic(
        data=[_to_request_public(item) for item in session.exec(data_query).all()],
        count=len(session.exec(count_query).all()),
    )


def list_all_requests(
    *,
    session: Session,
    status: AIAPIRequestStatus | None = None,
    skip: int = 0,
    limit: int = 100,
) -> AIAPIRequestsPublic:
    count_query = select(AIAPIRequest.id)
    data_query = select(AIAPIRequest)
    if status is not None:
        count_query = count_query.where(AIAPIRequest.status == status)
        data_query = data_query.where(AIAPIRequest.status == status)
    data_query = (
        data_query.order_by(AIAPIRequest.created_at.desc()).offset(skip).limit(limit)
    )
    return AIAPIRequestsPublic(
        data=[_to_request_public(item) for item in session.exec(data_query).all()],
        count=len(session.exec(count_query).all()),
    )


def get_request(
    *, session: Session, request_id: uuid.UUID, current_user
) -> AIAPIRequestPublic:
    db_request = session.get(AIAPIRequest, request_id)
    if not db_request:
        raise NotFoundError("AI API request not found")
    if not current_user.is_superuser and db_request.user_id != current_user.id:
        raise PermissionDeniedError("Not enough privileges")
    return _to_request_public(db_request)


def review_request(
    *,
    session: Session,
    request_id: uuid.UUID,
    review_data: AIAPIRequestReview,
    reviewer,
) -> AIAPIRequestPublic:
    db_request = session.get(AIAPIRequest, request_id)
    if not db_request:
        raise NotFoundError("AI API request not found")
    if db_request.status != AIAPIRequestStatus.pending:
        raise BadRequestError("This AI API request has already been reviewed")

    db_request.status = review_data.status
    db_request.reviewer_id = reviewer.id
    db_request.review_comment = (
        review_data.review_comment.strip() if review_data.review_comment else None
    )
    db_request.reviewed_at = get_datetime_utc()
    session.add(db_request)

    if review_data.status == AIAPIRequestStatus.approved:
        base_url = ai_api_settings.resolved_public_base_url
        api_key = _generate_user_api_key()
        if not base_url:
            raise BadRequestError("AI API connection settings are incomplete")

        expires_at = None
        now = get_datetime_utc()
        duration_str = db_request.duration
        if duration_str == "1h":
            expires_at = now + timedelta(hours=1)
        elif duration_str == "1d":
            expires_at = now + timedelta(days=1)
        elif duration_str == "7d":
            expires_at = now + timedelta(days=7)
        elif duration_str == "30d":
            expires_at = now + timedelta(days=30)

        session.add(
            AIAPICredential(
                user_id=db_request.user_id,
                request_id=db_request.id,
                base_url=base_url,
                api_key_encrypted=encrypt_value(api_key),
                api_key_prefix=_credential_prefix(api_key),
                api_key_name=db_request.api_key_name,
                rate_limit=db_request.rate_limit,  # 繼承申請的 rate_limit
                expires_at=expires_at,
            )
        )

    action = (
        "approved" if review_data.status == AIAPIRequestStatus.approved else "rejected"
    )
    details = f"Reviewed AI API request {request_id}: {action}"
    if db_request.review_comment:
        details += f". Comment: {db_request.review_comment}"
    audit_service.log_action(
        session=session,
        user_id=reviewer.id,
        action="ai_api_request_review",
        details=details,
        commit=False,
    )

    session.commit()
    session.refresh(db_request)
    logger.info("Admin %s %s AI API request %s", reviewer.email, action, request_id)
    return _to_request_public(db_request)


def list_credentials_by_user(
    *, session: Session, user_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> AIAPICredentialsPublic:
    count_query = select(AIAPICredential.id).where(AIAPICredential.user_id == user_id)
    data_query = (
        select(AIAPICredential)
        .where(AIAPICredential.user_id == user_id)
        .order_by(AIAPICredential.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return AIAPICredentialsPublic(
        data=[_to_credential_public(item) for item in session.exec(data_query).all()],
        count=len(session.exec(count_query).all()),
    )


def rotate_credential(
    *, session: Session, credential_id: uuid.UUID, current_user
) -> AIAPICredentialPublic:
    credential = _get_owned_credential(
        session=session, credential_id=credential_id, current_user=current_user
    )

    if credential.revoked_at is not None:
        raise BadRequestError("This AI API credential has already been revoked")

    credential.revoked_at = get_datetime_utc()
    session.add(credential)

    new_api_key = _generate_user_api_key()

    new_credential = AIAPICredential(
        user_id=credential.user_id,
        request_id=credential.request_id,
        base_url=credential.base_url,
        api_key_encrypted=encrypt_value(new_api_key),
        api_key_prefix=_credential_prefix(new_api_key),
        api_key_name=credential.api_key_name,
        rate_limit=credential.rate_limit,
        expires_at=credential.expires_at,
    )
    session.add(new_credential)

    audit_service.log_action(
        session=session,
        user_id=current_user.id,
        action="ai_api_request_review",
        details=f"Rotated AI API credential {credential_id}",
        commit=False,
    )

    session.commit()
    session.refresh(new_credential)
    return _to_credential_public(new_credential)


def delete_credential(
    *, session: Session, credential_id: uuid.UUID, current_user
) -> Message:
    credential = _get_owned_credential(
        session=session, credential_id=credential_id, current_user=current_user
    )

    session.delete(credential)
    audit_service.log_action(
        session=session,
        user_id=current_user.id,
        action="ai_api_request_review",
        details=f"Deleted AI API credential {credential_id}",
        commit=False,
    )
    session.commit()
    return Message(message="AI API credential deleted successfully")


def update_credential_name(
    *, session: Session, credential_id: uuid.UUID, name: str, current_user
) -> AIAPICredentialPublic:
    credential = _get_owned_credential(
        session=session, credential_id=credential_id, current_user=current_user
    )

    credential.api_key_name = name
    session.add(credential)

    audit_service.log_action(
        session=session,
        user_id=current_user.id,
        action="ai_api_request_review",
        details=f"Renamed AI API credential {credential_id} to '{name}'",
        commit=False,
    )

    session.commit()
    session.refresh(credential)
    return _to_credential_public(credential)


# ===== 新增：使用量记录功能 =====


def record_usage(
    *,
    session: Session,
    user_id: uuid.UUID,
    credential_id: uuid.UUID,
    model_name: str,
    request_type: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    request_duration_ms: int | None = None,
    status: str = "success",
    error_message: str | None = None,
) -> None:
    """
    记录 AI API 使用量

    Args:
        session: 数据库会话
        user_id: 用户 ID
        credential_id: 凭证 ID
        model_name: 模型名称
        request_type: 请求类型（chat_completion, completion等）
        prompt_tokens: 输入 tokens
        completion_tokens: 输出 tokens
        total_tokens: 总 tokens
        request_duration_ms: 请求耗时（毫秒）
        status: 状态（success, error）
        error_message: 错误信息
    """
    usage = AIAPIUsage(
        user_id=user_id,
        credential_id=credential_id,
        model_name=model_name,
        request_type=request_type,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        request_duration_ms=request_duration_ms,
        status=status,
        error_message=error_message,
    )
    session.add(usage)
    session.commit()
    logger.info(
        "Recorded usage for user %s: model=%s, tokens=%d",
        user_id,
        model_name,
        total_tokens,
    )


# ===== 新增：代理到 VLLM 功能 =====


async def proxy_to_vllm_chat_completion(
    *,
    user: User,
    request_data: dict,
) -> dict:
    """
    代理聊天补全請求到 VLLM Gateway（非流式）

    Returns:
        dict: VLLM 回應（附加 duration_ms 耗時資訊）
    """
    url = f"{ai_api_settings.resolved_vllm_base_url}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {ai_api_settings.ai_api_api_key}",
        "Content-Type": "application/json",
    }

    start_time = time.time()
    model_name = request_data.get("model", "unknown")

    try:
        async with httpx.AsyncClient(timeout=ai_api_settings.ai_api_timeout) as client:
            response = await client.post(url, json=request_data, headers=headers)
            response.raise_for_status()
            result = response.json()

        duration_ms = int((time.time() - start_time) * 1000)
        result["duration_ms"] = duration_ms  # 附加耗時到回應

        usage = result.get("usage", {})
        logger.info(
            "User %s completed chat request: model=%s, tokens=%d, duration=%dms",
            user.email,
            model_name,
            usage.get("total_tokens", 0),
            duration_ms,
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error(
            "VLLM request failed for user %s: %s",
            user.email,
            f"VLLM returned {e.response.status_code}: {e.response.text}",
        )
        raise

    except httpx.RequestError as e:
        logger.error("VLLM connection failed for user %s: %s", user.email, str(e))
        raise

    except Exception as e:
        logger.error("Unexpected error for user %s: %s", user.email, str(e))
        raise


async def proxy_to_vllm_chat_completion_stream(
    *,
    user: User,
    request_data: dict,
) -> AsyncGenerator[str, None]:
    """
    代理聊天补全請求到 VLLM Gateway（流式）

    流式回應的 usage 資訊已包含在 vLLM 传輸的各個 chunk 中（若模型支援）。
    """
    request_data["stream"] = True

    url = f"{ai_api_settings.resolved_vllm_base_url}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {ai_api_settings.ai_api_api_key}",
        "Content-Type": "application/json",
    }

    start_time = time.time()
    model_name = request_data.get("model", "unknown")

    try:
        async with httpx.AsyncClient(timeout=ai_api_settings.ai_api_timeout) as client:
            async with client.stream(
                "POST", url, json=request_data, headers=headers
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue

                    if line.startswith("data: "):
                        data_str = line[6:]

                        if data_str == "[DONE]":
                            duration_ms = int((time.time() - start_time) * 1000)
                            logger.info(
                                "User %s completed stream: model=%s, duration=%dms",
                                user.email,
                                model_name,
                                duration_ms,
                            )
                            yield "data: [DONE]\n\n"
                            break

                        try:
                            chunk = json.loads(data_str)
                            yield f"data: {json.dumps(chunk)}\n\n"
                        except json.JSONDecodeError:
                            yield f"data: {data_str}\n\n"

    except Exception as e:
        logger.error("Stream error for user %s: %s", user.email, str(e))
        raise


# ===== 新增：查询使用统计 =====


def get_user_usage_stats(
    *,
    session: Session,
    user_id: uuid.UUID,
    start_date: datetime,
    end_date: datetime,
) -> dict:
    """
    查询用户的使用统计

    Args:
        session: 数据库会话
        user_id: 用户 ID
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        dict: 统计信息
    """
    # 查询指定时间范围内的所有使用记录
    records = session.exec(
        select(AIAPIUsage)
        .where(AIAPIUsage.user_id == user_id)
        .where(AIAPIUsage.created_at >= start_date)
        .where(AIAPIUsage.created_at <= end_date)
    ).all()

    # 统计总数
    total_requests = len(records)
    total_tokens = sum(r.total_tokens for r in records)
    total_prompt_tokens = sum(r.prompt_tokens for r in records)
    total_completion_tokens = sum(r.completion_tokens for r in records)

    # 按模型分组统计
    by_model = {}
    for record in records:
        model = record.model_name
        if model not in by_model:
            by_model[model] = {
                "requests": 0,
                "tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
            }

        by_model[model]["requests"] += 1
        by_model[model]["tokens"] += record.total_tokens
        by_model[model]["prompt_tokens"] += record.prompt_tokens
        by_model[model]["completion_tokens"] += record.completion_tokens

    return {
        "total_requests": total_requests,
        "total_tokens": total_tokens,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "by_model": by_model,
        "start_date": start_date,
        "end_date": end_date,
    }
