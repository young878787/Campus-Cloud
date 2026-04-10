import logging
from typing import Annotated

import jwt
from fastapi import Depends, Query, WebSocket, WebSocketException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session

from app.api.deps.database import SessionDep, get_db
from app.core.authorizers import (
    require_admin_access,
    require_instructor_or_admin_access,
)
from app.core import security
from app.core.config import settings
from app.core.db import engine
from app.exceptions import AuthenticationError
from app.models import User
from app.schemas import TokenPayload

logger = logging.getLogger(__name__)

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)

TokenDep = Annotated[str, Depends(reusable_oauth2)]


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    # All failures here are authentication problems (bad/expired/revoked token,
    # missing or inactive user), so they must return 401 to trigger the
    # frontend refresh-token flow. Never raise 403 from this function — that
    # would incorrectly signal "authenticated but forbidden". The frontend
    # treats 403 as forbidden without logging the user out; 401 is what drives
    # token refresh and eventual logout if refresh fails.
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise AuthenticationError("Could not validate credentials")
    if token_data.type == "refresh":
        raise AuthenticationError("Refresh tokens cannot be used for API access")
    user = session.get(User, token_data.sub)
    if not user:
        raise AuthenticationError("User not found")
    if not user.is_active:
        raise AuthenticationError("Inactive user")
    if user.token_version != token_data.ver:
        raise AuthenticationError("Token has been revoked")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    require_admin_access(current_user)
    return current_user


AdminUser = Annotated[User, Depends(get_current_active_superuser)]


def get_current_instructor_or_admin(current_user: CurrentUser) -> User:
    require_instructor_or_admin_access(current_user)
    return current_user


InstructorUser = Annotated[User, Depends(get_current_instructor_or_admin)]


async def get_ws_current_user(
    websocket: WebSocket,
    token: str = Query(...),
) -> tuple[User, Session]:
    """Authenticate WebSocket connections via query-string token.
    Returns (user, session) so the caller can also check ownership."""
    # Reject empty or oversized tokens
    if not token or not token.strip():
        logger.warning("WebSocket connection attempted with empty token")
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    if len(token) > 4096:
        logger.warning("WebSocket connection attempted with oversized token")
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        logger.warning("WebSocket connection with invalid token")
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    session = Session(engine)
    try:
        user = session.get(User, token_data.sub)
        if not user or not user.is_active:
            logger.warning(f"WebSocket auth failed: user not found or inactive (sub={token_data.sub})")
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
        if user.token_version != token_data.ver:
            logger.warning(f"WebSocket auth failed: token version mismatch for user {user.email}")
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
        return user, session
    except Exception:
        session.close()
        raise
