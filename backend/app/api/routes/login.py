from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep, get_current_active_superuser
from app.schemas import Message, NewPassword, Token, UserPublic
from app.services import auth_service

router = APIRouter(tags=["login"])


@router.post("/login/access-token")
def login_access_token(
    session: SessionDep, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> Token:
    return auth_service.login(
        session=session, email=form_data.username, password=form_data.password
    )


class GoogleLoginRequest(BaseModel):
    id_token: str


@router.post("/login/google")
def login_google(session: SessionDep, body: GoogleLoginRequest) -> Token:
    return auth_service.google_login(session=session, id_token=body.id_token)


@router.post("/login/test-token", response_model=UserPublic)
def test_token(current_user: CurrentUser) -> Any:
    return current_user


@router.post("/password-recovery/{email}")
def recover_password(email: str, session: SessionDep) -> Message:
    auth_service.recover_password(session=session, email=email)
    return Message(
        message="If that email is registered, we sent a password recovery link"
    )


@router.post("/reset-password/")
def reset_password(session: SessionDep, body: NewPassword) -> Message:
    auth_service.reset_password(
        session=session, token=body.token, new_password=body.new_password
    )
    return Message(message="Password updated successfully")


@router.post(
    "/password-recovery-html-content/{email}",
    dependencies=[Depends(get_current_active_superuser)],
    response_class=HTMLResponse,
)
def recover_password_html_content(email: str, session: SessionDep) -> Any:
    html_content, subject = auth_service.get_password_recovery_html(
        session=session, email=email
    )
    return HTMLResponse(
        content=html_content, headers={"subject:": subject}
    )
