"""群組管理 API 路由"""

import uuid

from fastapi import APIRouter, HTTPException

from app.api.deps import InstructorUser, SessionDep
from app.exceptions import PermissionDeniedError
from app.repositories import group as group_repo
from app.schemas.common import Message
from app.schemas.group import (
    GroupCreate,
    GroupDetailPublic,
    GroupMemberAdd,
    GroupMemberPublic,
    GroupPublic,
    GroupsPublic,
)
from app.services import audit_service

router = APIRouter(prefix="/groups", tags=["groups"])


def _check_group_access(current_user, db_group) -> None:
    """確認使用者是群組擁有者或 admin，否則拋出例外"""
    if not current_user.is_superuser and db_group.owner_id != current_user.id:
        raise PermissionDeniedError("Not authorized to access this group")


@router.post("/", response_model=GroupPublic)
def create_group(
    group_in: GroupCreate,
    session: SessionDep,
    current_user: InstructorUser,
):
    db_group = group_repo.create_group(
        session=session,
        name=group_in.name,
        description=group_in.description,
        owner_id=current_user.id,
    )
    audit_service.log_action(
        session=session,
        user_id=current_user.id,
        action="group_create",
        details=f"Created group '{db_group.name}' (id={db_group.id})",
    )
    member_count = group_repo.count_members(session=session, group_id=db_group.id)
    return GroupPublic(
        id=db_group.id,
        name=db_group.name,
        description=db_group.description,
        owner_id=db_group.owner_id,
        created_at=db_group.created_at,
        member_count=member_count,
    )


@router.get("/", response_model=GroupsPublic)
def list_groups(session: SessionDep, current_user: InstructorUser):
    if current_user.is_superuser:
        groups = group_repo.get_all_groups(session=session)
    else:
        groups = group_repo.get_groups_by_owner(
            session=session, owner_id=current_user.id
        )
    data = [
        GroupPublic(
            id=g.id,
            name=g.name,
            description=g.description,
            owner_id=g.owner_id,
            created_at=g.created_at,
            member_count=group_repo.count_members(session=session, group_id=g.id),
        )
        for g in groups
    ]
    return GroupsPublic(data=data, count=len(data))


@router.get("/{group_id}", response_model=GroupDetailPublic)
def get_group(
    group_id: uuid.UUID, session: SessionDep, current_user: InstructorUser
):
    db_group = group_repo.get_group_by_id(session=session, group_id=group_id)
    if not db_group:
        raise HTTPException(status_code=404, detail="Group not found")
    _check_group_access(current_user, db_group)

    member_rows = group_repo.get_member_rows(session=session, group_id=group_id)
    members_map = {m.user_id: m for m in member_rows}
    users = group_repo.get_group_members(session=session, group_id=group_id)

    members_public = [
        GroupMemberPublic(
            user_id=u.id,
            email=u.email,
            full_name=u.full_name,
            added_at=members_map[u.id].added_at if u.id in members_map else None,
        )
        for u in users
    ]

    return GroupDetailPublic(
        id=db_group.id,
        name=db_group.name,
        description=db_group.description,
        owner_id=db_group.owner_id,
        created_at=db_group.created_at,
        members=members_public,
    )


@router.delete("/{group_id}", response_model=Message)
def delete_group(
    group_id: uuid.UUID, session: SessionDep, current_user: InstructorUser
):
    db_group = group_repo.get_group_by_id(session=session, group_id=group_id)
    if not db_group:
        raise HTTPException(status_code=404, detail="Group not found")
    _check_group_access(current_user, db_group)

    audit_service.log_action(
        session=session,
        user_id=current_user.id,
        action="group_delete",
        details=f"Deleted group '{db_group.name}' (id={group_id})",
    )
    group_repo.delete_group(session=session, group_id=group_id)
    return Message(message="Group deleted")


@router.post("/{group_id}/members", response_model=Message)
def add_members(
    group_id: uuid.UUID,
    body: GroupMemberAdd,
    session: SessionDep,
    current_user: InstructorUser,
):
    db_group = group_repo.get_group_by_id(session=session, group_id=group_id)
    if not db_group:
        raise HTTPException(status_code=404, detail="Group not found")
    _check_group_access(current_user, db_group)

    added, not_found = group_repo.add_members_by_emails(
        session=session, group_id=group_id, emails=body.emails
    )

    audit_service.log_action(
        session=session,
        user_id=current_user.id,
        action="group_member_add",
        details=(
            f"Added {len(added)} member(s) to group '{db_group.name}'"
            + (f"; not found: {not_found}" if not_found else "")
        ),
    )

    msg = f"Added {len(added)} member(s)"
    if not_found:
        msg += f". Not found: {', '.join(not_found)}"
    return Message(message=msg)


@router.delete("/{group_id}/members/{user_id}", response_model=Message)
def remove_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    session: SessionDep,
    current_user: InstructorUser,
):
    db_group = group_repo.get_group_by_id(session=session, group_id=group_id)
    if not db_group:
        raise HTTPException(status_code=404, detail="Group not found")
    _check_group_access(current_user, db_group)

    removed = group_repo.remove_member(
        session=session, group_id=group_id, user_id=user_id
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Member not found in group")

    audit_service.log_action(
        session=session,
        user_id=current_user.id,
        action="group_member_remove",
        details=f"Removed user {user_id} from group '{db_group.name}'",
    )
    return Message(message="Member removed")


