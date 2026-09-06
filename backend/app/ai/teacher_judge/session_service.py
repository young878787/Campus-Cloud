"""Persistent Teacher Judge session workflow."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlmodel import Session, col, desc, func, select

from app.ai.teacher_judge.attachment_service import (
    attachment_context,
    attachment_public,
    storage_path,
)
from app.ai.teacher_judge.file_service import (
    FileDeleteStage,
    _stored_path,
    _unlink_if_exists,
    clone_file_asset,
    finalize_file_delete,
    restore_file_delete,
    stage_file_delete,
)
from app.ai.teacher_judge.schemas import (
    TeacherJudgeRubricChatMessage,
    TeacherJudgeSessionMessagePublic,
    TeacherJudgeSessionPublic,
)
from app.ai.teacher_judge.service import chat_with_rubric
from app.ai.teacher_judge.template_command_service import get_enabled_template_commands
from app.core.i18n import t
from app.models.teacher_judge_attachment import TeacherJudgeSessionAttachment
from app.models.teacher_judge_file import TeacherJudgeFile, TeacherJudgeFileStatus
from app.models.teacher_judge_script_artifact import TeacherJudgeScriptArtifact
from app.models.teacher_judge_script_run import TeacherJudgeScriptRun
from app.models.teacher_judge_session import (
    TeacherJudgeMessageRole,
    TeacherJudgeMessageType,
    TeacherJudgeSession,
    TeacherJudgeSessionMessage,
    TeacherJudgeSessionStatus,
)
from app.models.teacher_judge_template_command import TeacherJudgeTemplateCommand

HISTORY_MESSAGE_LIMIT = 20
HISTORY_CHARACTER_LIMIT = 24000
SUMMARY_TURN_INTERVAL = 10
_SENSITIVE_PATTERNS = (
    re.compile(
        r"(?i)\b(password|passwd|token|secret|api[_-]?key|authorization)\b"
        r"(\s*[:=]\s*)([^\s,;]+)"
    ),
    # 有界量詞避免 polynomial ReDoS（CodeQL py/polynomial-redos）：
    # header 詞彙固定為大寫（RSA/EC/OPENSSH/ENCRYPTED…），本體長度設上限
    re.compile(
        r"-----BEGIN [A-Z ]{0,40}PRIVATE KEY-----"
        r"[\s\S]{0,16384}?"
        r"-----END [A-Z ]{0,40}PRIVATE KEY-----"
    ),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def redact_message_content(value: str) -> str:
    redacted = value
    redacted = _SENSITIVE_PATTERNS[0].sub(r"\1\2[REDACTED]", redacted)
    redacted = _SENSITIVE_PATTERNS[1].sub("[REDACTED PRIVATE KEY]", redacted)
    return redacted


def require_selected_file(db: Session, item: TeacherJudgeSession) -> TeacherJudgeFile:
    if not item.selected_file_id:
        raise HTTPException(status_code=409, detail=t("session.no_rubric_selected"))
    file = db.get(TeacherJudgeFile, item.selected_file_id)
    if (
        not file
        or file.teaching_class_id != item.teaching_class_id
        or file.status != TeacherJudgeFileStatus.active
    ):
        raise HTTPException(
            status_code=409, detail=t("session.selected_file_unavailable")
        )
    return file


def selected_file_for_chat(
    db: Session, item: TeacherJudgeSession
) -> TeacherJudgeFile | None:
    """Return the selected rubric when present; a chat can start without one."""
    if not item.selected_file_id:
        return None
    return require_selected_file(db, item)


def get_session(
    db: Session, class_id: uuid.UUID, session_id: uuid.UUID
) -> TeacherJudgeSession:
    item = db.get(TeacherJudgeSession, session_id)
    if not item or item.teaching_class_id != class_id:
        raise HTTPException(status_code=404, detail=t("session.not_found"))
    return item


def delete_session_data(db: Session, item: TeacherJudgeSession) -> None:
    """Delete a session and its private rubric, messages, scripts, and runs."""
    source_file_stage: FileDeleteStage | None = None
    attachment_rows = list(
        db.exec(
            select(TeacherJudgeSessionAttachment).where(
                TeacherJudgeSessionAttachment.session_id == item.id
            )
        )
    )
    try:
        if item.selected_file_id:
            source_file = db.get(TeacherJudgeFile, item.selected_file_id)
            if (
                source_file is not None
                and source_file.teaching_class_id == item.teaching_class_id
            ):
                # A unique DB index prevents this for new data.  The guard keeps a
                # legacy shared row from being removed underneath another session
                # if deletion runs before the ownership migration is applied.
                other_session = db.exec(
                    select(TeacherJudgeSession).where(
                        TeacherJudgeSession.selected_file_id == source_file.id,
                        TeacherJudgeSession.id != item.id,
                    )
                ).first()
                if other_session is None:
                    source_file_stage = stage_file_delete(
                        session=db, file=source_file
                    )

        artifacts = list(
            db.exec(
                select(TeacherJudgeScriptArtifact).where(
                    TeacherJudgeScriptArtifact.session_id == item.id
                )
            )
        )
        for artifact in artifacts:
            runs = list(
                db.exec(
                    select(TeacherJudgeScriptRun).where(
                        TeacherJudgeScriptRun.artifact_id == artifact.id
                    )
                )
            )
            for run in runs:
                db.delete(run)

        messages = list(
            db.exec(
                select(TeacherJudgeSessionMessage).where(
                    TeacherJudgeSessionMessage.session_id == item.id
                )
            )
        )
        for attachment in attachment_rows:
            db.delete(attachment)
        for message in messages:
            db.delete(message)
        for artifact in artifacts:
            db.delete(artifact)

        db.delete(item)
        db.commit()
    except Exception:
        db.rollback()
        restore_file_delete(source_file_stage)
        raise
    else:
        finalize_file_delete(source_file_stage)
        for attachment in attachment_rows:
            try:
                storage_path(attachment).unlink(missing_ok=True)
            except OSError:
                # 附件實體檔刪不掉不影響 DB 刪除，留給清理排程處理
                pass


def clear_session_messages(db: Session, item: TeacherJudgeSession) -> None:
    """Clear conversation history while keeping the session and its artifacts."""
    attachments = list(
        db.exec(
            select(TeacherJudgeSessionAttachment).where(
                TeacherJudgeSessionAttachment.session_id == item.id
            )
        )
    )
    messages = list(
        db.exec(
            select(TeacherJudgeSessionMessage).where(
                TeacherJudgeSessionMessage.session_id == item.id
            )
        )
    )
    for attachment in attachments:
        db.delete(attachment)
    for message in messages:
        db.delete(message)

    now = _now()
    item.summary = ""
    item.updated_at = now
    item.last_activity_at = now
    db.add(item)
    db.commit()
    db.refresh(item)
    for attachment in attachments:
        try:
            storage_path(attachment).unlink(missing_ok=True)
        except OSError:
            # 附件實體檔刪不掉不影響 DB 狀態，留給清理排程處理
            pass


def ensure_selected_file_available(
    db: Session,
    file_id: uuid.UUID,
    *,
    exclude_session_id: uuid.UUID | None = None,
) -> None:
    """Reject attaching a rubric that another session already owns.

    Session fork is the explicit copy boundary.  Regular create/update flows
    may claim an unassigned class file, but they never silently clone or share
    a source with another session.
    """
    statement = select(TeacherJudgeSession).where(
        TeacherJudgeSession.selected_file_id == file_id
    )
    if exclude_session_id is not None:
        statement = statement.where(TeacherJudgeSession.id != exclude_session_id)
    owner = db.exec(statement).first()
    if owner is None:
        return
    raise HTTPException(
        status_code=409,
        detail={
            "code": "teacher_judge_file_in_use",
            "message": t("session.file_in_use"),
            "session_id": str(owner.id),
        },
    )


def ensure_active(item: TeacherJudgeSession) -> None:
    if item.status == TeacherJudgeSessionStatus.archived:
        raise HTTPException(status_code=409, detail=t("session.archived_readonly"))


def validate_selected_file(
    db: Session, class_id: uuid.UUID, file_id: uuid.UUID | None
) -> None:
    if file_id is None:
        return
    file = db.get(TeacherJudgeFile, file_id)
    if (
        not file
        or file.teaching_class_id != class_id
        or file.status != TeacherJudgeFileStatus.active
    ):
        raise HTTPException(
            status_code=400,
            detail=t("session.file_not_in_class"),
        )


def _session_public(
    item: TeacherJudgeSession,
    *,
    file: TeacherJudgeFile | None,
    message_count: int,
    script_count: int,
    run_count: int,
) -> TeacherJudgeSessionPublic:
    return TeacherJudgeSessionPublic(
        id=str(item.id),
        teaching_class_id=str(item.teaching_class_id),
        teaching_class_week_id=(
            str(item.teaching_class_week_id) if item.teaching_class_week_id else None
        ),
        title=item.title,
        status=item.status.value,
        selected_file_id=str(item.selected_file_id) if item.selected_file_id else None,
        selected_file_name=(file.display_name or file.original_filename) if file else None,
        selected_file_item_count=(
            len(file.analysis_json.get("items", []))
            if file and isinstance(file.analysis_json, dict)
            and isinstance(file.analysis_json.get("items"), list)
            else None
        ),
        template_key=file.template_key if file else None,
        summary=item.summary,
        message_count=message_count,
        script_count=script_count,
        run_count=run_count,
        created_by=str(item.created_by) if item.created_by else None,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
        last_activity_at=item.last_activity_at.isoformat(),
        pinned_at=item.pinned_at.isoformat() if item.pinned_at else None,
    )


def session_public(db: Session, item: TeacherJudgeSession) -> TeacherJudgeSessionPublic:
    """Build one public session without changing the existing response contract."""
    file = (
        db.get(TeacherJudgeFile, item.selected_file_id)
        if item.selected_file_id
        else None
    )
    message_count = db.exec(
        select(func.count())
        .select_from(TeacherJudgeSessionMessage)
        .where(TeacherJudgeSessionMessage.session_id == item.id)
    ).one()
    script_count = db.exec(
        select(func.count())
        .select_from(TeacherJudgeScriptArtifact)
        .where(TeacherJudgeScriptArtifact.session_id == item.id)
    ).one()
    run_count = db.exec(
        select(func.count())
        .select_from(TeacherJudgeScriptRun)
        .join(TeacherJudgeScriptArtifact)
        .where(TeacherJudgeScriptArtifact.session_id == item.id)
    ).one()
    return _session_public(
        item,
        file=file,
        message_count=message_count,
        script_count=script_count,
        run_count=run_count,
    )


def session_public_many(
    db: Session, items: Sequence[TeacherJudgeSession]
) -> list[TeacherJudgeSessionPublic]:
    """Build list responses with batched file and count lookups."""
    if not items:
        return []
    session_ids = list(dict.fromkeys(item.id for item in items))
    file_ids = list(
        dict.fromkeys(
            item.selected_file_id for item in items if item.selected_file_id is not None
        )
    )
    files_by_id = {
        row.id: row
        for row in (
            db.exec(
                select(TeacherJudgeFile).where(col(TeacherJudgeFile.id).in_(file_ids))
            ).all()
            if file_ids
            else []
        )
    }
    message_counts = dict(
        db.exec(
            select(col(TeacherJudgeSessionMessage.session_id), func.count())
            .where(col(TeacherJudgeSessionMessage.session_id).in_(session_ids))
            .group_by(col(TeacherJudgeSessionMessage.session_id))
        ).all()
    )
    script_counts = dict(
        db.exec(
            select(col(TeacherJudgeScriptArtifact.session_id), func.count())
            .where(col(TeacherJudgeScriptArtifact.session_id).in_(session_ids))
            .group_by(col(TeacherJudgeScriptArtifact.session_id))
        ).all()
    )
    run_counts = dict(
        db.exec(
            select(
                col(TeacherJudgeScriptArtifact.session_id),
                func.count(col(TeacherJudgeScriptRun.id)),
            )
            .select_from(TeacherJudgeScriptRun)
            .join(
                TeacherJudgeScriptArtifact,
                col(TeacherJudgeScriptRun.artifact_id)
                == col(TeacherJudgeScriptArtifact.id),
            )
            .where(col(TeacherJudgeScriptArtifact.session_id).in_(session_ids))
            .group_by(col(TeacherJudgeScriptArtifact.session_id))
        ).all()
    )
    return [
        _session_public(
            item,
            file=(
                files_by_id.get(item.selected_file_id)
                if item.selected_file_id is not None
                else None
            ),
            message_count=message_counts.get(item.id, 0),
            script_count=script_counts.get(item.id, 0),
            run_count=run_counts.get(item.id, 0),
        )
        for item in items
    ]


def _fork_title(db: Session, class_id: uuid.UUID, title: str) -> str:
    base = f"{title}（副本）"
    existing = {
        row.title
        for row in db.exec(
            select(TeacherJudgeSession).where(
                TeacherJudgeSession.teaching_class_id == class_id
            )
        )
    }
    if base not in existing:
        return base
    for index in range(2, 1000):
        candidate = f"{title}（副本 {index}）"
        if candidate not in existing:
            return candidate
    raise HTTPException(status_code=409, detail=t("session.fork_title_exhausted"))


def fork_session_data(
    db: Session,
    source: TeacherJudgeSession,
    *,
    title: str | None,
    created_by: uuid.UUID | None,
) -> TeacherJudgeSession:
    """Clone editable settings only; history and execution evidence stay behind."""
    cloned_file: TeacherJudgeFile | None = None
    try:
        if source.selected_file_id:
            source_file = db.get(TeacherJudgeFile, source.selected_file_id)
            if (
                source_file is None
                or source_file.teaching_class_id != source.teaching_class_id
                or source_file.status != TeacherJudgeFileStatus.active
            ):
                raise HTTPException(
                    status_code=409, detail=t("session.fork_file_unavailable")
                )
            cloned_file = clone_file_asset(
                session=db,
                source=source_file,
                teaching_class_id=source.teaching_class_id,
                created_by=created_by,
            )
        clone = TeacherJudgeSession(
            teaching_class_id=source.teaching_class_id,
            teaching_class_week_id=source.teaching_class_week_id,
            title=(title.strip() if title else _fork_title(db, source.teaching_class_id, source.title)),
            status=TeacherJudgeSessionStatus.active,
            selected_file_id=cloned_file.id if cloned_file else None,
            summary="",
            created_by=created_by,
        )
        db.add(clone)
        db.commit()
        db.refresh(clone)
        return clone
    except Exception:
        db.rollback()
        if cloned_file and cloned_file.original_filename:
            _unlink_if_exists(_stored_path(cloned_file.id, cloned_file.original_filename))
        raise


def message_attachments(
    db: Session, message_id: uuid.UUID
) -> list[TeacherJudgeSessionAttachment]:
    return list(
        db.exec(
            select(TeacherJudgeSessionAttachment)
            .where(TeacherJudgeSessionAttachment.message_id == message_id)
            .order_by(
                col(TeacherJudgeSessionAttachment.created_at),
                col(TeacherJudgeSessionAttachment.id),
            )
        )
    )


def message_attachments_by_message_ids(
    db: Session, message_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[TeacherJudgeSessionAttachment]]:
    """Load message attachments in one query for list/history responses."""
    unique_ids = list(dict.fromkeys(message_ids))
    if not unique_ids:
        return {}
    rows = list(
        db.exec(
            select(TeacherJudgeSessionAttachment)
            .where(col(TeacherJudgeSessionAttachment.message_id).in_(unique_ids))
            .order_by(
                col(TeacherJudgeSessionAttachment.created_at),
                col(TeacherJudgeSessionAttachment.id),
            )
        )
    )
    grouped: dict[uuid.UUID, list[TeacherJudgeSessionAttachment]] = {}
    for row in rows:
        if row.message_id is not None:
            grouped.setdefault(row.message_id, []).append(row)
    return grouped


def message_public(
    item: TeacherJudgeSessionMessage,
    attachments: list[TeacherJudgeSessionAttachment] | None = None,
) -> TeacherJudgeSessionMessagePublic:
    return TeacherJudgeSessionMessagePublic(
        id=str(item.id),
        session_id=str(item.session_id),
        role=item.role.value,
        content=item.content,
        message_type=item.message_type.value,
        metadata_json=item.metadata_json,
        attachments=[attachment_public(row) for row in attachments or []],
        created_by=str(item.created_by) if item.created_by else None,
        created_at=item.created_at.isoformat(),
    )


def _message_context(
    db: Session,
    row: TeacherJudgeSessionMessage,
    *,
    include_attachments: bool = True,
    attachments: list[TeacherJudgeSessionAttachment] | None = None,
) -> str:
    if not include_attachments:
        return row.content
    attachment_rows = (
        attachments if attachments is not None else message_attachments(db, row.id)
    )
    if not attachment_rows:
        return row.content
    return f"{row.content}\n\n{attachment_context(attachment_rows)}"


def bounded_history(
    db: Session,
    session_id: uuid.UUID,
    *,
    exclude_attachments_for_message_id: uuid.UUID | None = None,
) -> list[TeacherJudgeRubricChatMessage]:
    rows = list(
        db.exec(
            select(TeacherJudgeSessionMessage)
            .where(
                TeacherJudgeSessionMessage.session_id == session_id,
                TeacherJudgeSessionMessage.message_type
                != TeacherJudgeMessageType.system_notice,
            )
            .order_by(
                desc(TeacherJudgeSessionMessage.created_at),
                desc(TeacherJudgeSessionMessage.id),
            )
            .limit(HISTORY_MESSAGE_LIMIT)
        )
    )
    rows.reverse()
    attachments_by_message_id = message_attachments_by_message_ids(
        db, [row.id for row in rows]
    )
    # Build each message's full content at most once. The trim pass and the
    # response pass previously rebuilt the same attachment context strings,
    # doubling join/slice work for every kept message.
    content_by_id: dict[uuid.UUID, str] = {}
    kept: list[TeacherJudgeSessionMessage] = []
    size = 0
    for row in reversed(rows):
        if row.id not in content_by_id:
            content_by_id[row.id] = _message_context(
                db,
                row,
                include_attachments=row.id != exclude_attachments_for_message_id,
                attachments=attachments_by_message_id.get(row.id, []),
            )
        content = content_by_id[row.id]
        if kept and size + len(content) > HISTORY_CHARACTER_LIMIT:
            break
        kept.append(row)
        size += len(content)
    return [
        TeacherJudgeRubricChatMessage(
            role=row.role.value,
            content=content_by_id[row.id],
        )
        for row in reversed(kept)
    ]


async def maybe_summarize(
    db: Session,
    item: TeacherJudgeSession,
    file: TeacherJudgeFile | None,
    *,
    template_commands: list[TeacherJudgeTemplateCommand] | None = None,
) -> None:
    assistant_count = db.exec(
        select(func.count())
        .select_from(TeacherJudgeSessionMessage)
        .where(
            TeacherJudgeSessionMessage.session_id == item.id,
            TeacherJudgeSessionMessage.role == TeacherJudgeMessageRole.assistant,
            TeacherJudgeSessionMessage.message_type
            != TeacherJudgeMessageType.system_notice,
        )
    ).one()
    if not assistant_count or assistant_count % SUMMARY_TURN_INTERVAL:
        return
    messages = bounded_history(db, item.id)
    messages.append(
        TeacherJudgeRubricChatMessage(
            role="user",
            content="請將以上最近十輪對話與既有摘要壓縮為簡短繁體中文工作摘要，只回傳摘要文字。既有摘要："
            + item.summary,
        )
    )
    try:
        rubric_context = json.dumps(file.analysis_json, ensure_ascii=False) if file else "{}"
        template_key = file.template_key if file else "linux"
        # Reuse the chat request's catalog when provided so a summary turn does
        # not issue the same enabled-commands query twice in one request.
        resolved_commands = (
            template_commands
            if template_commands is not None
            else get_enabled_template_commands(
                db, template_key, include_cross_template=True
            )
        )
        reply, _, _ = await chat_with_rubric(
            messages,
            rubric_context,
            is_refine=False,
            template_key=template_key,
            template_commands=resolved_commands,
            environment_keys=file.environment_keys if file else None,
        )
    except Exception:
        return
    item.summary = reply[:12000]
    item.updated_at = _now()
    db.add(item)
    db.commit()
