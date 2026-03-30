from datetime import timedelta

import httpx
from sqlmodel import Session

from app.core import security
from app.core.config import settings
from app.exceptions import BadRequestError, NotFoundError
from app.schemas import Token, UserUpdate
from app.repositories import user as user_repo
from app.utils import (
    generate_password_reset_token,
    generate_reset_password_email,
    send_email,
    verify_password_reset_token,
)


def login(*, session: Session, email: str, password: str) -> Token:
    user = user_repo.authenticate(session=session, email=email, password=password)
    if not user:
        raise BadRequestError("Incorrect email or password")
    if not user.is_active:
        raise BadRequestError("Inactive user")
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return Token(
        access_token=security.create_access_token(
            user.id, expires_delta=access_token_expires
        )
    )


def google_login(*, session: Session, id_token: str) -> Token:
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": id_token},
            )
    except httpx.RequestError as exc:
        # Ensure network/timeout issues become deterministic application errors
        raise BadRequestError("Unable to verify Google token") from exc
    if r.status_code != 200:
        raise BadRequestError("Invalid Google token")
    data = r.json()
    if settings.GOOGLE_CLIENT_ID and data.get("aud") != settings.GOOGLE_CLIENT_ID:
        raise BadRequestError("Invalid Google token audience")
    email_verified_raw = data.get("email_verified")
    if isinstance(email_verified_raw, bool):
        email_verified = email_verified_raw
    elif isinstance(email_verified_raw, str):
        email_verified = email_verified_raw.lower() == "true"
    else:
        email_verified = False
    if not email_verified:
        raise BadRequestError("Google email not verified")
    email = data.get("email")
    if not email:
        raise BadRequestError("Could not retrieve email from Google token")
    user = user_repo.get_user_by_email(session=session, email=email)
    if not user:
        raise BadRequestError("Invalid Google token")
    if not user.is_active:
        raise BadRequestError("Inactive user")
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return Token(
        access_token=security.create_access_token(
            user.id, expires_delta=access_token_expires
        )
    )


def recover_password(*, session: Session, email: str) -> None:
    user = user_repo.get_user_by_email(session=session, email=email)
    if user:
        token = generate_password_reset_token(email=email)
        email_data = generate_reset_password_email(
            email_to=user.email, email=email, token=token
        )
        send_email(
            email_to=user.email,
            subject=email_data.subject,
            html_content=email_data.html_content,
        )


def reset_password(*, session: Session, token: str, new_password: str) -> None:
    email = verify_password_reset_token(token=token)
    if not email:
        raise BadRequestError("Invalid token")
    user = user_repo.get_user_by_email(session=session, email=email)
    if not user:
        raise BadRequestError("Invalid token")
    if not user.is_active:
        raise BadRequestError("Inactive user")
    user_repo.update_user(
        session=session, db_user=user, user_in=UserUpdate(password=new_password)
    )
    session.commit()


def get_password_recovery_html(
    *, session: Session, email: str
) -> tuple[str, str]:
    """Returns (html_content, subject) for password recovery email."""
    user = user_repo.get_user_by_email(session=session, email=email)
    if not user:
        raise NotFoundError(
            "The user with this username does not exist in the system."
        )
    token = generate_password_reset_token(email=email)
    email_data = generate_reset_password_email(
        email_to=user.email, email=email, token=token
    )
    return email_data.html_content, email_data.subject
