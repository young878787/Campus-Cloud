from typing import Any

from sqlmodel import Session, select

from app.core.security import get_password_hash, verify_password
from app.models import User, UserRole
from app.schemas import UserCreate, UserUpdate


def _resolve_role_fields(
    *,
    role: UserRole | None,
    is_superuser: bool,
    is_instructor: bool,
) -> tuple[UserRole, bool, bool]:
    if role is None:
        if is_superuser:
            role = UserRole.admin
        elif is_instructor:
            role = UserRole.teacher
        else:
            role = UserRole.student
    elif is_superuser and role != UserRole.admin:
        # Explicit is_superuser=True overrides role default to admin.
        role = UserRole.admin

    if role == UserRole.admin:
        return role, True, False
    if role == UserRole.teacher:
        return role, False, False
    return role, False, False


def create_user(*, session: Session, user_create: UserCreate) -> User:
    role, is_superuser, is_instructor = _resolve_role_fields(
        role=user_create.role,
        is_superuser=user_create.is_superuser,
        is_instructor=False,
    )
    db_obj = User.model_validate(
        user_create,
        update={
            "role": role,
            "is_superuser": is_superuser,
            "is_instructor": is_instructor,
            "hashed_password": get_password_hash(user_create.password),
        },
    )
    session.add(db_obj)
    session.flush()
    return db_obj


def update_user(*, session: Session, db_user: User, user_in: UserUpdate) -> Any:
    user_data = user_in.model_dump(exclude_unset=True)
    extra_data = {}
    if "password" in user_data:
        password = user_data["password"]
        hashed_password = get_password_hash(password)
        extra_data["hashed_password"] = hashed_password
    role, is_superuser, is_instructor = _resolve_role_fields(
        role=user_data.get("role", db_user.role),
        is_superuser=user_data.get("is_superuser", db_user.is_superuser),
        is_instructor=db_user.is_instructor,
    )
    extra_data["role"] = role
    extra_data["is_superuser"] = is_superuser
    extra_data["is_instructor"] = is_instructor
    db_user.sqlmodel_update(user_data, update=extra_data)
    session.add(db_user)
    session.flush()
    return db_user


def get_user_by_email(*, session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    return session.exec(statement).first()


# Dummy hash for timing attack prevention when user is not found
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


def authenticate(*, session: Session, email: str, password: str) -> User | None:
    db_user = get_user_by_email(session=session, email=email)
    if not db_user:
        verify_password(password, DUMMY_HASH)
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        db_user.hashed_password = updated_password_hash
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
    return db_user
