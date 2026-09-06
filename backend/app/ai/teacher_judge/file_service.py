"""Teacher Judge uploaded rubric file lifecycle service."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, desc, func, select

from app.ai.teacher_judge.schemas import (
    TeacherJudgeFileMetadataUpdateRequest,
    TeacherJudgeFilePublic,
    TeacherJudgeFileSourceTypeLiteral,
    TeacherJudgeRubricAnalysis,
)
from app.ai.teacher_judge.template_command_service import SUPPORTED_TEMPLATE_KEYS
from app.core.i18n import t
from app.models.teacher_judge_file import TeacherJudgeFile, TeacherJudgeFileStatus
from app.models.teacher_judge_script_artifact import TeacherJudgeScriptArtifact
from app.models.teacher_judge_session import TeacherJudgeSession
from app.services.rubric_parser import parse_document

ConflictStrategy = Literal["overwrite", "copy"]

DATA_ROOT = Path(__file__).resolve().parents[4] / "data" / "teacher-judge" / "files"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FileDeleteStage:
    """Filesystem paths moved aside while a file row is deleted transactionally."""

    path: Path | None
    deleted_path: Path | None


def _now() -> datetime:
    from app.models.base import get_datetime_utc

    return get_datetime_utc()


def _safe_filename(filename: str) -> str:
    # 去掉路徑片段後，再移除控制字元（CR/LF 等），避免之後作為
    # Content-Disposition 檔名或寫入日誌時被夾帶額外內容
    name = Path(filename or "rubric").name
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    return name or "rubric"


def _display_name_from_filename(filename: str) -> str:
    """Return a readable rubric name while keeping the original filename separate."""
    stem = Path(filename or "").stem.strip()
    return stem or "評分表"


def _suffix(filename: str) -> str:
    return Path(filename).suffix.lower()


def _stored_path(file_id: uuid.UUID, original_filename: str) -> Path:
    return DATA_ROOT / f"{file_id}{_suffix(original_filename)}"


def _temp_path(file_id: uuid.UUID, original_filename: str) -> Path:
    return DATA_ROOT / f"{file_id}{_suffix(original_filename)}.tmp"


def _backup_path(file_id: uuid.UUID, original_filename: str) -> Path:
    return DATA_ROOT / f"{file_id}{_suffix(original_filename)}.bak"


def _deleted_path(file_id: uuid.UUID, original_filename: str) -> Path:
    return DATA_ROOT / f"{file_id}{_suffix(original_filename)}.deleted"


def _unlink_if_exists(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        logger.warning("Failed to remove Teacher Judge file path: %s", path)


def _raise_name_conflict(existing: TeacherJudgeFile | None = None) -> None:
    detail: dict[str, str] = {
        "code": "teacher_judge_file_name_conflict",
        "message": t("file.name_conflict"),
    }
    if existing is not None:
        detail["file_id"] = str(existing.id)
        detail["original_filename"] = existing.original_filename or ""
    raise HTTPException(
        status_code=409,
        detail=detail,
    )


def _file_to_public(file: TeacherJudgeFile) -> TeacherJudgeFilePublic:
    return TeacherJudgeFilePublic(
        id=str(file.id),
        teaching_class_id=str(file.teaching_class_id),
        uploaded_by=str(file.uploaded_by) if file.uploaded_by else None,
        original_filename=file.original_filename,
        file_hash=file.file_hash,
        template_key=file.template_key,
        source_type=cast(TeacherJudgeFileSourceTypeLiteral, file.source_type),
        display_name=file.display_name or file.original_filename or "評分表",
        environment_keys=list(file.environment_keys or [file.template_key]),
        analysis_revision=file.analysis_revision,
        analysis_json=file.analysis_json,
        status=file.status.value,
        created_at=file.created_at.isoformat(),
        updated_at=file.updated_at.isoformat(),
    )


def _active_file_by_name(
    *,
    session: Session,
    teaching_class_id: uuid.UUID,
    original_filename: str,
    for_update: bool = False,
) -> TeacherJudgeFile | None:
    statement = select(TeacherJudgeFile).where(
        TeacherJudgeFile.teaching_class_id == teaching_class_id,
        TeacherJudgeFile.original_filename == original_filename,
        TeacherJudgeFile.status == TeacherJudgeFileStatus.active,
    )
    if for_update:
        statement = statement.with_for_update()
    return session.exec(statement).first()


def raise_if_file_name_conflict(
    *,
    session: Session,
    teaching_class_id: uuid.UUID,
    original_filename: str,
    conflict_strategy: ConflictStrategy | None,
) -> None:
    if conflict_strategy is not None:
        return
    existing = _active_file_by_name(
        session=session,
        teaching_class_id=teaching_class_id,
        original_filename=original_filename,
    )
    if existing is None:
        return
    _raise_name_conflict(existing)


def _linked_script_count(*, session: Session, file_id: uuid.UUID) -> int:
    count = session.exec(
        select(func.count()).select_from(TeacherJudgeScriptArtifact).where(
            TeacherJudgeScriptArtifact.source_file_id == file_id
        )
    ).one()
    return int(count or 0)


def _copy_filename(
    *,
    session: Session,
    teaching_class_id: uuid.UUID,
    original_filename: str,
) -> str:
    path = Path(original_filename)
    stem = path.stem or "rubric"
    suffix = path.suffix
    existing = set(
        session.exec(
            select(TeacherJudgeFile.original_filename).where(
                TeacherJudgeFile.teaching_class_id == teaching_class_id
            )
        ).all()
    )
    for index in range(2, 1000):
        candidate = f"{stem} ({index}){suffix}"
        if candidate not in existing:
            return candidate
    raise HTTPException(status_code=409, detail=t("file.copy_name_exhausted"))


def _file_snapshot(file: TeacherJudgeFile | None) -> dict[str, Any]:
    if file is None:
        return {}
    return {
        "id": str(file.id),
        "original_filename": file.original_filename,
        "file_hash": file.file_hash,
        "template_key": file.template_key,
        "status": file.status.value,
        "created_at": file.created_at.isoformat(),
        "updated_at": file.updated_at.isoformat(),
    }


def list_files(
    *,
    session: Session,
    teaching_class_id: uuid.UUID,
) -> list[TeacherJudgeFilePublic]:
    files = session.exec(
        select(TeacherJudgeFile)
        .where(TeacherJudgeFile.teaching_class_id == teaching_class_id)
        .order_by(desc(TeacherJudgeFile.created_at))
    ).all()
    return [_file_to_public(file) for file in files]


def get_file(
    *,
    session: Session,
    teaching_class_id: uuid.UUID,
    file_id: uuid.UUID,
) -> TeacherJudgeFile:
    file = session.get(TeacherJudgeFile, file_id)
    if file is None or file.teaching_class_id != teaching_class_id:
        raise HTTPException(status_code=404, detail=t("file.not_found"))
    return file


def get_file_download(
    *,
    session: Session,
    teaching_class_id: uuid.UUID,
    file_id: uuid.UUID,
) -> tuple[Path, str]:
    file = get_file(session=session, teaching_class_id=teaching_class_id, file_id=file_id)
    if file.source_type == "created" or not file.original_filename:
        raise HTTPException(
            status_code=409, detail=t("file.created_no_document")
        )
    path = _stored_path(file.id, file.original_filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=t("file.original_missing"))
    return path, file.original_filename


def prepare_file_payload(
    *,
    filename: str,
    file_bytes: bytes,
    allowed_suffixes: set[str],
    max_upload_size_bytes: int,
) -> tuple[str, str, str]:
    original_filename = _safe_filename(filename)
    suffix = _suffix(original_filename)
    if suffix not in allowed_suffixes:
        raise HTTPException(
            status_code=415,
            detail=t(
                "file.unsupported_format",
                suffix=suffix,
                allowed=", ".join(sorted(allowed_suffixes)),
            ),
        )
    if len(file_bytes) > max_upload_size_bytes:
        file_size_mb = len(file_bytes) / (1024 * 1024)
        max_size_mb = max_upload_size_bytes / (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=t(
                "file.size_exceeded",
                size=f"{file_size_mb:.1f}",
                max_size=f"{max_size_mb:.0f}",
            ),
        )
    if not file_bytes:
        raise HTTPException(status_code=400, detail=t("file.empty_upload"))
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    raw_text = parse_document(original_filename, file_bytes)
    if not raw_text.strip():
        raise HTTPException(
            status_code=422,
            detail=t("file.no_extractable_text"),
        )
    return original_filename, file_hash, raw_text


def save_analyzed_file(
    *,
    session: Session,
    teaching_class_id: uuid.UUID,
    uploaded_by: uuid.UUID | None,
    original_filename: str,
    file_hash: str,
    template_key: str,
    file_bytes: bytes,
    analysis: TeacherJudgeRubricAnalysis,
    conflict_strategy: ConflictStrategy | None,
    environment_keys: list[str] | None = None,
    display_name: str | None = None,
) -> TeacherJudgeFilePublic:
    existing = _active_file_by_name(
        session=session,
        teaching_class_id=teaching_class_id,
        original_filename=original_filename,
        for_update=conflict_strategy == "overwrite",
    )
    target_filename = original_filename
    target_file: TeacherJudgeFile | None = None
    now = _now()

    if existing is not None and conflict_strategy is None:
        # `existing` already proves the active-name conflict; reuse it instead
        # of a second identical `_active_file_by_name` SELECT via
        # `raise_if_file_name_conflict` (same 409 payload, one fewer query).
        _raise_name_conflict(existing)

    # Single Pydantic serialization / env normalization shared by the create
    # and overwrite-reuse branches below (only one branch runs per call).
    analysis_json = analysis.model_dump(mode="json")
    normalized_environment_keys = list(dict.fromkeys(environment_keys or [template_key]))

    if existing is not None and conflict_strategy == "copy":
        target_filename = _copy_filename(
            session=session,
            teaching_class_id=teaching_class_id,
            original_filename=original_filename,
        )
    elif existing is not None and conflict_strategy == "overwrite":
        if _linked_script_count(session=session, file_id=existing.id) > 0:
            existing.status = TeacherJudgeFileStatus.replaced
            existing.updated_at = now
            session.add(existing)
        else:
            target_file = existing

    if target_file is None:
        target_file = TeacherJudgeFile(
            teaching_class_id=teaching_class_id,
            uploaded_by=uploaded_by,
            original_filename=target_filename,
            file_hash=file_hash,
            template_key=template_key,
            source_type="uploaded",
            display_name=display_name or _display_name_from_filename(original_filename),
            environment_keys=list(normalized_environment_keys),
            analysis_revision=1,
            analysis_json=dict(analysis_json),
            status=TeacherJudgeFileStatus.active,
            updated_at=now,
        )
    else:
        target_file.uploaded_by = uploaded_by
        target_file.file_hash = file_hash
        target_file.template_key = template_key
        target_file.source_type = "uploaded"
        target_file.display_name = display_name or _display_name_from_filename(target_filename)
        target_file.environment_keys = list(normalized_environment_keys)
        target_file.analysis_revision = int(target_file.analysis_revision or 1) + 1
        target_file.analysis_json = dict(analysis_json)
        target_file.status = TeacherJudgeFileStatus.active
        target_file.updated_at = now
        target_file.original_filename = target_filename

    session.add(target_file)
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    session.flush()

    assert target_file.original_filename is not None
    final_path = _stored_path(target_file.id, target_file.original_filename)
    temp_path = _temp_path(target_file.id, target_file.original_filename)
    backup_path = _backup_path(target_file.id, target_file.original_filename)
    backed_up_existing = False
    try:
        temp_path.write_bytes(file_bytes)
        if final_path.exists():
            _unlink_if_exists(backup_path)
            os.replace(final_path, backup_path)
            backed_up_existing = True
        os.replace(temp_path, final_path)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        _unlink_if_exists(final_path)
        if backed_up_existing and backup_path.exists():
            os.replace(backup_path, final_path)
        _raise_name_conflict()
        raise AssertionError("unreachable") from exc
    except Exception:
        session.rollback()
        _unlink_if_exists(temp_path)
        _unlink_if_exists(final_path)
        if backed_up_existing and backup_path.exists():
            os.replace(backup_path, final_path)
        raise
    else:
        _unlink_if_exists(backup_path)
    session.refresh(target_file)
    return _file_to_public(target_file)


def update_file_analysis(
    *,
    session: Session,
    teaching_class_id: uuid.UUID,
    file_id: uuid.UUID,
    analysis: TeacherJudgeRubricAnalysis,
    expected_revision: int | None = None,
) -> TeacherJudgeFilePublic:
    file = get_file(session=session, teaching_class_id=teaching_class_id, file_id=file_id)
    if file.status != TeacherJudgeFileStatus.active:
        raise HTTPException(
            status_code=409, detail=t("file.replaced_choose_active")
        )
    if expected_revision is not None and file.analysis_revision != expected_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "teacher_judge_analysis_revision_conflict",
                "message": t("file.revision_conflict"),
                "analysis_revision": file.analysis_revision,
            },
        )
    file.analysis_json = analysis.model_dump(mode="json")
    file.analysis_revision = int(file.analysis_revision or 1) + 1
    file.updated_at = _now()
    session.add(file)
    session.commit()
    session.refresh(file)
    return _file_to_public(file)


def create_blank_file(
    *,
    session: Session,
    teaching_class_id: uuid.UUID,
    created_by: uuid.UUID | None,
    display_name: str,
    environment_keys: list[str],
) -> TeacherJudgeFile:
    """Create an editable, class-scoped rubric without an uploaded document.

    The caller owns the transaction.  The returned row has been flushed but is
    not committed, allowing session creation and rubric creation to succeed or
    roll back together.
    """
    name = display_name.strip()
    normalized = list(dict.fromkeys(key.strip().lower() for key in environment_keys if key.strip()))
    if not name:
        raise HTTPException(status_code=422, detail=t("file.blank_name"))
    if not normalized or any(key not in SUPPORTED_TEMPLATE_KEYS for key in normalized):
        raise HTTPException(
            status_code=422, detail=t("file.no_environment_selected")
        )
    analysis = TeacherJudgeRubricAnalysis()
    item = TeacherJudgeFile(
        teaching_class_id=teaching_class_id,
        uploaded_by=created_by,
        original_filename=None,
        file_hash=None,
        template_key=normalized[0],
        source_type="created",
        display_name=name,
        environment_keys=normalized,
        analysis_json=analysis.model_dump(mode="json"),
        analysis_revision=1,
        status=TeacherJudgeFileStatus.active,
        updated_at=_now(),
    )
    session.add(item)
    session.flush()
    return item


def update_file_metadata(
    *,
    session: Session,
    teaching_class_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: TeacherJudgeFileMetadataUpdateRequest,
) -> TeacherJudgeFilePublic:
    file = get_file(session=session, teaching_class_id=teaching_class_id, file_id=file_id)
    if file.status != TeacherJudgeFileStatus.active:
        raise HTTPException(
            status_code=409, detail=t("file.replaced_cannot_edit")
        )
    if payload.display_name is not None:
        file.display_name = payload.display_name
    if payload.environment_keys is not None:
        file.environment_keys = payload.environment_keys
        if payload.template_key is None:
            file.template_key = payload.environment_keys[0]
    if payload.template_key is not None:
        if payload.template_key not in (file.environment_keys or [payload.template_key]):
            raise HTTPException(
                status_code=422, detail=t("file.template_key_not_in_candidates")
            )
        file.template_key = payload.template_key
    file.updated_at = _now()
    session.add(file)
    session.commit()
    session.refresh(file)
    return _file_to_public(file)


def clone_file_asset(
    *,
    session: Session,
    source: TeacherJudgeFile,
    teaching_class_id: uuid.UUID,
    created_by: uuid.UUID | None,
) -> TeacherJudgeFile:
    """Clone a rubric asset, including upload bytes when available.

    Database changes are flushed but left to the caller's transaction.  Any
    staged file is removed if writing fails, so a fork cannot leave a half-file.
    """
    if source.teaching_class_id != teaching_class_id:
        raise HTTPException(status_code=404, detail=t("file.not_found"))
    copied_filename: str | None = None
    source_path: Path | None = None
    if source.source_type == "uploaded":
        if not source.original_filename or not source.file_hash:
            raise HTTPException(
                status_code=409, detail=t("file.clone_info_incomplete")
            )
        source_path = _stored_path(source.id, source.original_filename)
        if not source_path.is_file():
            raise HTTPException(
                status_code=404, detail=t("file.clone_original_missing")
            )
        copied_filename = _copy_filename(
            session=session,
            teaching_class_id=teaching_class_id,
            original_filename=source.original_filename,
        )
    display_name = source.display_name or source.original_filename or "評分表"
    clone = TeacherJudgeFile(
        teaching_class_id=teaching_class_id,
        uploaded_by=created_by,
        original_filename=copied_filename,
        file_hash=source.file_hash,
        template_key=source.template_key,
        source_type=source.source_type,
        display_name=f"{display_name}（副本）",
        environment_keys=list(source.environment_keys or [source.template_key]),
        analysis_json=deepcopy(source.analysis_json),
        analysis_revision=1,
        status=TeacherJudgeFileStatus.active,
        updated_at=_now(),
    )
    session.add(clone)
    session.flush()
    if source.source_type != "uploaded":
        return clone

    assert copied_filename is not None
    assert source.original_filename is not None
    assert source_path is not None
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    final_path = _stored_path(clone.id, copied_filename)
    temp_path = _temp_path(clone.id, copied_filename)
    try:
        shutil.copyfile(source_path, temp_path)
        os.replace(temp_path, final_path)
    except Exception:
        _unlink_if_exists(temp_path)
        _unlink_if_exists(final_path)
        raise
    return clone


def stage_file_delete(
    *,
    session: Session,
    file: TeacherJudgeFile,
) -> FileDeleteStage:
    """Stage a rubric row and its stored bytes for deletion.

    The database row is marked for deletion but not committed.  Callers that
    own a larger transaction can commit the row together with its parent
    session, then call :func:`finalize_file_delete`; on rollback call
    :func:`restore_file_delete` to put the bytes back.
    """
    path = (
        _stored_path(file.id, file.original_filename)
        if file.original_filename
        else None
    )
    deleted_path = (
        _deleted_path(file.id, file.original_filename)
        if file.original_filename
        else None
    )
    if path is not None and path.exists():
        assert deleted_path is not None
        _unlink_if_exists(deleted_path)
        os.replace(path, deleted_path)

    linked_artifacts = session.exec(
        select(TeacherJudgeScriptArtifact).where(
            TeacherJudgeScriptArtifact.source_file_id == file.id
        )
    ).all()
    for artifact in linked_artifacts:
        artifact.source_file_id = None
        session.add(artifact)

    # Keep the DB consistent even when a backend is configured without
    # foreign-key enforcement (for example, SQLite test databases).
    linked_sessions = session.exec(
        select(TeacherJudgeSession).where(
            TeacherJudgeSession.selected_file_id == file.id
        )
    ).all()
    for linked_session in linked_sessions:
        linked_session.selected_file_id = None
        linked_session.updated_at = _now()
        linked_session.last_activity_at = linked_session.updated_at
        session.add(linked_session)

    session.delete(file)
    return FileDeleteStage(path=path, deleted_path=deleted_path)


def finalize_file_delete(stage: FileDeleteStage | None) -> None:
    """Remove bytes that were staged after the owning DB transaction commits."""
    if stage is not None and stage.deleted_path is not None:
        _unlink_if_exists(stage.deleted_path)


def restore_file_delete(stage: FileDeleteStage | None) -> None:
    """Restore bytes staged by :func:`stage_file_delete` after rollback."""
    if (
        stage is None
        or stage.path is None
        or stage.deleted_path is None
        or not stage.deleted_path.exists()
    ):
        return
    stage.path.parent.mkdir(parents=True, exist_ok=True)
    _unlink_if_exists(stage.path)
    os.replace(stage.deleted_path, stage.path)


def delete_file(
    *,
    session: Session,
    teaching_class_id: uuid.UUID,
    file_id: uuid.UUID,
) -> None:
    file = get_file(session=session, teaching_class_id=teaching_class_id, file_id=file_id)
    stage: FileDeleteStage | None = None
    try:
        stage = stage_file_delete(session=session, file=file)
        session.commit()
    except Exception:
        session.rollback()
        restore_file_delete(stage)
        raise
    finalize_file_delete(stage)


def source_file_snapshot(
    *,
    session: Session,
    teaching_class_id: uuid.UUID,
    file_id: uuid.UUID | None,
) -> tuple[TeacherJudgeFile | None, dict[str, Any]]:
    if file_id is None:
        return None, {}
    file = get_file(session=session, teaching_class_id=teaching_class_id, file_id=file_id)
    return file, _file_snapshot(file)


def parse_conflict_strategy(value: str | None) -> ConflictStrategy | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip().lower()
    if normalized not in {"overwrite", "copy"}:
        raise HTTPException(
            status_code=400, detail=t("file.unknown_conflict_strategy")
        )
    return cast("ConflictStrategy", normalized)
