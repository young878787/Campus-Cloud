import uuid
from typing import Any

from sqlmodel import Session, func, select

from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from app.models import User
from app.schemas import (
    UserCreate,
    UserRegister,
    UserUpdate,
    UserUpdateMe,
    UsersPublic,
)
from app.repositories import user as user_repo
from app.services import audit_service
from app.utils import generate_new_account_email, send_email


def list_users(*, session: Session, skip: int = 0, limit: int = 100) -> UsersPublic:
    count = session.exec(select(func.count()).select_from(User)).one()
    users = session.exec(
        select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
    ).all()
    return UsersPublic(data=users, count=count)


def create_user(
    *, session: Session, user_in: UserCreate, current_user_id: uuid.UUID
) -> User:
    existing = user_repo.get_user_by_email(session=session, email=user_in.email)
    if existing:
        raise ConflictError("The user with this email already exists in the system.")

    user = user_repo.create_user(session=session, user_create=user_in)

    audit_service.log_action(
        session=session,
        user_id=current_user_id,
        action="user_create",
        details=f"Created user: {user_in.email}, is_superuser: {user_in.is_superuser}",
    )

    if settings.emails_enabled and user_in.email:
        email_data = generate_new_account_email(
            email_to=user_in.email, username=user_in.email, password=user_in.password
        )
        send_email(
            email_to=user_in.email,
            subject=email_data.subject,
            html_content=email_data.html_content,
        )
    return user


def register_user(*, session: Session, user_in: UserRegister) -> User:
    existing = user_repo.get_user_by_email(session=session, email=user_in.email)
    if existing:
        raise ConflictError("The user with this email already exists in the system")
    user_create = UserCreate.model_validate(user_in.model_dump())
    return user_repo.create_user(session=session, user_create=user_create)


def get_user_by_id(
    *, session: Session, user_id: uuid.UUID, current_user: User
) -> User:
    user = session.get(User, user_id)
    if user == current_user:
        return user
    if not current_user.is_superuser:
        raise PermissionDeniedError("The user doesn't have enough privileges")
    if not user:
        raise NotFoundError("User not found")
    return user


def update_user(
    *,
    session: Session,
    user_id: uuid.UUID,
    user_in: UserUpdate,
    current_user_id: uuid.UUID,
) -> User:
    db_user = session.get(User, user_id)
    if not db_user:
        raise NotFoundError("The user with this id does not exist in the system")
    if user_in.email:
        existing = user_repo.get_user_by_email(session=session, email=user_in.email)
        if existing and existing.id != user_id:
            raise ConflictError("User with this email already exists")

    db_user = user_repo.update_user(session=session, db_user=db_user, user_in=user_in)

    changes = ", ".join(
        f"{k}={v}" for k, v in user_in.model_dump(exclude_unset=True).items()
    )
    audit_service.log_action(
        session=session,
        user_id=current_user_id,
        action="user_update",
        details=f"Updated user {db_user.email}: {changes}",
    )
    return db_user


def delete_user(*, session: Session, user_id: uuid.UUID, current_user: User) -> None:
    user = session.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    if user == current_user:
        raise PermissionDeniedError(
            "Super users are not allowed to delete themselves"
        )

    audit_service.log_action(
        session=session,
        user_id=current_user.id,
        action="user_delete",
        details=f"Deleted user: {user.email}",
    )
    session.delete(user)
    session.commit()


def update_me(*, session: Session, user_in: UserUpdateMe, current_user: User) -> User:
    if user_in.email:
        existing = user_repo.get_user_by_email(session=session, email=user_in.email)
        if existing and existing.id != current_user.id:
            raise ConflictError("User with this email already exists")

    user_data = user_in.model_dump(exclude_unset=True)
    current_user.sqlmodel_update(user_data)
    session.add(current_user)
    session.commit()
    session.refresh(current_user)

    changes = ", ".join(f"{k}={v}" for k, v in user_data.items())
    audit_service.log_action(
        session=session,
        user_id=current_user.id,
        action="user_update",
        details=f"Updated own profile: {changes}",
    )
    return current_user


def update_password(
    *, session: Session, current_password: str, new_password: str, current_user: User
) -> None:
    verified, _ = verify_password(current_password, current_user.hashed_password)
    if not verified:
        raise BadRequestError("Incorrect password")
    if current_password == new_password:
        raise BadRequestError(
            "New password cannot be the same as the current one"
        )
    current_user.hashed_password = get_password_hash(new_password)
    session.add(current_user)
    session.commit()


def delete_me(*, session: Session, current_user: User) -> None:
    if current_user.is_superuser:
        raise PermissionDeniedError(
            "Super users are not allowed to delete themselves"
        )

    audit_service.log_action(
        session=session,
        user_id=current_user.id,
        action="user_delete",
        details=f"Deleted own account: {current_user.email}",
    )
    session.delete(current_user)
    session.commit()
