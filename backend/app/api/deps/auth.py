from typing import Annotated

import jwt
from fastapi import Depends, Query, WebSocket, WebSocketException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session

from app.api.deps.database import SessionDep, get_db
from app.core import security
from app.core.config import settings
from app.exceptions import PermissionDeniedError
from app.models import User
from app.schemas import TokenPayload

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)

TokenDep = Annotated[str, Depends(reusable_oauth2)]


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise PermissionDeniedError("Could not validate credentials")
    user = session.get(User, token_data.sub)
    if not user:
        raise PermissionDeniedError("User not found")
    if not user.is_active:
        raise PermissionDeniedError("Inactive user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise PermissionDeniedError("The user doesn't have enough privileges")
    return current_user


AdminUser = Annotated[User, Depends(get_current_active_superuser)]


async def get_ws_current_user(
    websocket: WebSocket,
    token: str = Query(...),
) -> tuple[User, Session]:
    """Authenticate WebSocket connections via query-string token.
    Returns (user, session) so the caller can also check ownership."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    session = next(get_db())
    user = session.get(User, token_data.sub)
    if not user or not user.is_active:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    return user, session
