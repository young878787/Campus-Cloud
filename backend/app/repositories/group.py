"""群組相關資料庫操作"""

import uuid
from datetime import datetime, timezone

from sqlmodel import Session, func, select

from app.models.batch_provision import (
    BatchProvisionJob,
    BatchProvisionTask,
    BatchProvisionTaskStatus,
)
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.resource import Resource
from app.models.user import User


def create_group(
    *,
    session: Session,
    name: str,
    description: str | None,
    owner_id: uuid.UUID,
) -> Group:
    db_group = Group(
        name=name,
        description=description,
        owner_id=owner_id,
        created_at=datetime.now(timezone.utc),
    )
    session.add(db_group)
    session.commit()
    session.refresh(db_group)
    return db_group


def get_group_by_id(*, session: Session, group_id: uuid.UUID) -> Group | None:
    return session.exec(select(Group).where(Group.id == group_id)).first()


def get_groups_by_owner(*, session: Session, owner_id: uuid.UUID) -> list[Group]:
    return list(session.exec(select(Group).where(Group.owner_id == owner_id)).all())


def get_all_groups(*, session: Session) -> list[Group]:
    return list(session.exec(select(Group)).all())


def delete_group(*, session: Session, group_id: uuid.UUID) -> None:
    db_group = get_group_by_id(session=session, group_id=group_id)
    if db_group:
        session.delete(db_group)
        session.commit()


def get_group_members(*, session: Session, group_id: uuid.UUID) -> list[User]:
    """回傳群組內所有 User 物件"""
    members = list(
        session.exec(select(GroupMember).where(GroupMember.group_id == group_id)).all()
    )
    user_ids = [m.user_id for m in members]
    if not user_ids:
        return []
    return list(session.exec(select(User).where(User.id.in_(user_ids))).all())


def get_member_rows(*, session: Session, group_id: uuid.UUID) -> list[GroupMember]:
    """回傳群組成員的 GroupMember rows（含 added_at）"""
    return list(
        session.exec(select(GroupMember).where(GroupMember.group_id == group_id)).all()
    )


def add_members_by_emails(
    *, session: Session, group_id: uuid.UUID, emails: list[str]
) -> tuple[list[GroupMember], list[str]]:
    added: list[GroupMember] = []
    not_found: list[str] = []

    existing_members = {
        m.user_id
        for m in session.exec(
            select(GroupMember).where(GroupMember.group_id == group_id)
        ).all()
    }

    # Use a single query to fetch all users whose emails are in the list,
    # then do in-memory lookups to avoid N+1 queries.
    users = list(session.exec(select(User).where(User.email.in_(emails))).all())
    users_by_email = {u.email: u for u in users}

    for email in emails:
        user = users_by_email.get(email)
        if not user:
            not_found.append(email)
            continue
        if user.id in existing_members:
            continue
        gm = GroupMember(
            group_id=group_id,
            user_id=user.id,
            added_at=datetime.now(timezone.utc),
        )
        session.add(gm)
        added.append(gm)
        existing_members.add(user.id)

    session.commit()
    return added, not_found


def remove_member(*, session: Session, group_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """移除成員，回傳是否成功找到並刪除"""
    gm = session.exec(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id,
        )
    ).first()
    if not gm:
        return False
    session.delete(gm)
    session.commit()
    return True


def get_group_member_user_ids_for_instructor(
    *, session: Session, instructor_id: uuid.UUID
) -> list[uuid.UUID]:
    """取得老師所有群組中，學生的 user_id 清單（老師防火牆可見範圍）"""
    # 取得老師管理的群組
    groups = list(
        session.exec(select(Group).where(Group.owner_id == instructor_id)).all()
    )
    if not groups:
        return []
    group_ids = [g.id for g in groups]

    # 取得這些群組中的所有成員 user_id（排除老師本人）
    members = list(
        session.exec(
            select(GroupMember).where(GroupMember.group_id.in_(group_ids))
        ).all()
    )
    user_ids = [m.user_id for m in members if m.user_id != instructor_id]
    return list(set(user_ids))


def is_user_in_any_owned_group(
    *,
    session: Session,
    instructor_id: uuid.UUID,
    member_user_id: uuid.UUID,
) -> bool:
    """檢查 member_user_id 是否在 instructor_id 管理的任意群組中"""
    groups = list(
        session.exec(select(Group).where(Group.owner_id == instructor_id)).all()
    )
    if not groups:
        return False
    group_ids = [g.id for g in groups]
    gm = session.exec(
        select(GroupMember).where(
            GroupMember.group_id.in_(group_ids),
            GroupMember.user_id == member_user_id,
        )
    ).first()
    return gm is not None


def count_members(*, session: Session, group_id: uuid.UUID) -> int:
    return session.exec(
        select(func.count())
        .select_from(GroupMember)
        .where(GroupMember.group_id == group_id)
    ).one()


def get_member_counts(
    *, session: Session, group_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not group_ids:
        return {}
    rows = session.exec(
        select(GroupMember.group_id, func.count())
        .where(GroupMember.group_id.in_(group_ids))
        .group_by(GroupMember.group_id)
    ).all()
    return dict(rows)


def get_member_vmids(
    *, session: Session, group_id: uuid.UUID
) -> dict[uuid.UUID, int | None]:
    """取得群組中每個成員最新一次成功批量建立的 vmid。

    回傳 {user_id: vmid}，沒有成功建立過的成員不會出現在 dict 中。
    查詢邏輯：找該群組所有 batch_provision_jobs，取每個成員最新
    completed task 的 vmid。
    """
    # 子查詢：該群組所有 job id
    job_ids_stmt = select(BatchProvisionJob.id).where(
        BatchProvisionJob.group_id == group_id
    )

    # 取出所有屬於該群組的 completed tasks（含 vmid）
    stmt = (
        select(
            BatchProvisionTask.user_id,
            BatchProvisionTask.vmid,
            BatchProvisionTask.finished_at,
        )
        .where(
            BatchProvisionTask.job_id.in_(job_ids_stmt),
            BatchProvisionTask.status == BatchProvisionTaskStatus.completed,
            BatchProvisionTask.vmid.is_not(None),
        )
        .order_by(BatchProvisionTask.finished_at.desc())
    )
    rows = session.exec(stmt).all()

    vmids = {vmid for _, vmid, _ in rows if vmid is not None}
    if not vmids:
        return {}

    resource_rows = session.exec(
        select(Resource.vmid, Resource.user_id, Resource.created_at).where(
            Resource.vmid.in_(vmids)
        )
    ).all()
    resources_by_vmid = {
        vmid: (owner_id, created_at)
        for vmid, owner_id, created_at in resource_rows
    }

    # 每個 user_id 只取最新一筆
    result: dict[uuid.UUID, int | None] = {}
    for user_id, vmid, finished_at in rows:
        if user_id not in result:
            if vmid is None:
                continue

            resource_meta = resources_by_vmid.get(vmid)
            if resource_meta is None:
                continue

            owner_id, created_at = resource_meta
            if owner_id != user_id:
                continue

            # VMID may be reused after the original batch-created resource was deleted.
            # If the current resource was created after the task completed, ignore it.
            if (
                finished_at is not None
                and created_at is not None
                and created_at > finished_at
            ):
                continue

            result[user_id] = vmid
    return result
