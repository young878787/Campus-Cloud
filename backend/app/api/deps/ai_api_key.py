"""
AI API Key 认证依赖
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlmodel import select

from app.api.deps.database import SessionDep
from app.core.security import decrypt_value
from app.models import AIAPICredential, User, get_datetime_utc


def get_current_user_by_ai_api_key(
    session: SessionDep,
    authorization: str = Header(..., description="Bearer ccai_xxx"),
) -> tuple[User, AIAPICredential]:
    """
    通过 AI API Key (ccai_xxx) 验证用户身份

    Returns:
        tuple[User, AIAPICredential]: 用户对象和凭证对象

    Raises:
        HTTPException: 401 如果认证失败
    """
    # 1. 提取 token
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected: Bearer <api_key>",
        )

    api_key = authorization.replace("Bearer ", "").strip()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is required",
        )

    # 2. 用 prefix 縮小查詢範圍（前 8 字元）
    api_key_prefix = api_key[: min(8, len(api_key))]

    candidates = session.exec(
        select(AIAPICredential)
        .where(AIAPICredential.api_key_prefix == api_key_prefix)
        .where(AIAPICredential.revoked_at.is_(None))
    ).all()

    # 3. 逐一解密比對，找到真正匹配的憑證
    credential = None
    for cand in candidates:
        try:
            decrypted_key = decrypt_value(cand.api_key_encrypted)
            if decrypted_key == api_key:
                credential = cand
                break
        except Exception:
            continue

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
        )

    # 4. 检查过期
    if credential.expires_at and credential.expires_at < get_datetime_utc():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired",
        )

    # 5. 获取用户并检查状态
    user = session.get(User, credential.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
        )

    return user, credential


# 类型标注（用于依赖注入）
AIAPIUserDep = Annotated[
    tuple[User, AIAPICredential], Depends(get_current_user_by_ai_api_key)
]


__all__ = ["get_current_user_by_ai_api_key", "AIAPIUserDep"]
