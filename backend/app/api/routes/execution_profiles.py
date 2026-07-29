"""系統管理員維護執行環境設定檔。"""

import uuid

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app.api.deps import AdminUser, SessionDep
from app.models.execution_profile import ExecutionProfile, ExecutionProfileCommand
from app.schemas.execution_profile import (
    ExecutionProfileCommandCreate,
    ExecutionProfileCommandPublic,
    ExecutionProfileCommandUpdate,
    ExecutionProfileCreate,
    ExecutionProfilePublic,
    ExecutionProfileUpdate,
)

router = APIRouter(prefix="/execution-profiles", tags=["execution-profiles"])


def _profile_or_404(session: SessionDep, profile_id: uuid.UUID) -> ExecutionProfile:
    profile = session.get(ExecutionProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Execution profile not found")
    return profile


@router.get("/", response_model=list[ExecutionProfilePublic])
def list_profiles(session: SessionDep, _: AdminUser) -> list[ExecutionProfile]:
    return list(session.exec(select(ExecutionProfile).order_by(ExecutionProfile.profile_key)))


@router.post("/", response_model=ExecutionProfilePublic, status_code=201)
def create_profile(
    body: ExecutionProfileCreate, session: SessionDep, _: AdminUser
) -> ExecutionProfile:
    profile = ExecutionProfile.model_validate(body)
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


@router.patch("/{profile_id}", response_model=ExecutionProfilePublic)
def update_profile(
    profile_id: uuid.UUID,
    body: ExecutionProfileUpdate,
    session: SessionDep,
    _: AdminUser,
) -> ExecutionProfile:
    profile = _profile_or_404(session, profile_id)
    profile.sqlmodel_update(body.model_dump(exclude_unset=True))
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


@router.get(
    "/{profile_id}/commands",
    response_model=list[ExecutionProfileCommandPublic],
)
def list_commands(
    profile_id: uuid.UUID, session: SessionDep, _: AdminUser
) -> list[ExecutionProfileCommand]:
    _profile_or_404(session, profile_id)
    statement = (
        select(ExecutionProfileCommand)
        .where(ExecutionProfileCommand.profile_id == profile_id)
        .order_by(
            ExecutionProfileCommand.category,
            ExecutionProfileCommand.command_key,
        )
    )
    return list(session.exec(statement))


@router.post(
    "/{profile_id}/commands",
    response_model=ExecutionProfileCommandPublic,
    status_code=201,
)
def create_command(
    profile_id: uuid.UUID,
    body: ExecutionProfileCommandCreate,
    session: SessionDep,
    _: AdminUser,
) -> ExecutionProfileCommand:
    _profile_or_404(session, profile_id)
    command = ExecutionProfileCommand(profile_id=profile_id, **body.model_dump())
    session.add(command)
    session.commit()
    session.refresh(command)
    return command


@router.patch(
    "/{profile_id}/commands/{command_id}",
    response_model=ExecutionProfileCommandPublic,
)
def update_command(
    profile_id: uuid.UUID,
    command_id: uuid.UUID,
    body: ExecutionProfileCommandUpdate,
    session: SessionDep,
    _: AdminUser,
) -> ExecutionProfileCommand:
    command = session.get(ExecutionProfileCommand, command_id)
    if command is None or command.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="Execution profile command not found")
    command.sqlmodel_update(body.model_dump(exclude_unset=True))
    session.add(command)
    session.commit()
    session.refresh(command)
    return command
