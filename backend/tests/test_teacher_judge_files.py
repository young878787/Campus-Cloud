from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from app.ai.teacher_judge import file_service, script_artifact_service, session_service
from app.ai.teacher_judge.schemas import (
    RubricAnalysis,
    RubricItem,
    TeacherJudgeFileMetadataUpdateRequest,
)
from app.api.routes.teacher_judge_files import _normalize_supported_environment_keys
from app.models.teacher_judge_file import TeacherJudgeFile, TeacherJudgeFileStatus
from app.models.teacher_judge_script_artifact import (
    TeacherJudgeScriptArtifact,
    TeacherJudgeScriptStatus,
)
from app.models.teacher_judge_session import TeacherJudgeSession

SAFE_SCRIPT = """
import json
print(json.dumps({
    "schema_version": "teacher_judge_result.v1",
    "metadata": {},
    "summary": "ok",
    "checks": [],
    "errors": [],
}, ensure_ascii=False))
""".strip()


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _analysis(summary: str = "rubric") -> RubricAnalysis:
    return RubricAnalysis(
        items=[
            RubricItem(
                id="item-1",
                title="Web UI",
                description="確認服務可存取",
                checked=False,
                detectable="auto",
                detection_method="檢查 localhost",
                fallback=None,
                check_steps=[
                    {
                        "template_key": "linux",
                        "command_key": "system.run_command",
                        "parameters": {
                            "argv": ["ss", "-lnt"],
                            "timeout_seconds": 10,
                            "success_criteria": "命令成功並取得 listening sockets",
                        },
                    }
                ],
            )
        ],
        total_items=1,
        auto_count=1,
        summary=summary,
    )


def test_active_file_by_name_can_lock_existing_row_for_overwrite() -> None:
    captured_statement: Any = None

    class Result:
        def first(self) -> None:
            return None

    class DummySession:
        def exec(self, statement: Any) -> Result:
            nonlocal captured_statement
            captured_statement = statement
            return Result()

    file_service._active_file_by_name(
        session=DummySession(),
        teaching_class_id=uuid.uuid4(),
        original_filename="rubric.pdf",
        for_update=True,
    )

    assert captured_statement is not None
    assert getattr(captured_statement, "_for_update_arg", None) is not None


def test_save_file_requires_conflict_strategy_for_same_active_name(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(file_service, "DATA_ROOT", tmp_path)
    session = _session()
    teaching_class_id = uuid.uuid4()

    first = file_service.save_analyzed_file(
        session=session,
        teaching_class_id=teaching_class_id,
        uploaded_by=uuid.uuid4(),
        original_filename="rubric.pdf",
        file_hash="a" * 64,
        template_key="linux",
        file_bytes=b"one",
        analysis=_analysis("one"),
        conflict_strategy=None,
    )

    with pytest.raises(HTTPException) as exc_info:
        file_service.save_analyzed_file(
            session=session,
            teaching_class_id=teaching_class_id,
            uploaded_by=uuid.uuid4(),
            original_filename="rubric.pdf",
            file_hash="b" * 64,
            template_key="linux",
            file_bytes=b"two",
            analysis=_analysis("two"),
            conflict_strategy=None,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["file_id"] == first.id


def test_uploaded_file_display_name_uses_filename_stem(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(file_service, "DATA_ROOT", tmp_path)
    session = _session()

    saved = file_service.save_analyzed_file(
        session=session,
        teaching_class_id=uuid.uuid4(),
        uploaded_by=uuid.uuid4(),
        original_filename="AI評分表審核系統_Python服務Running狀態檢測_簡短版.docx",
        file_hash="a" * 64,
        template_key="python",
        file_bytes=b"document",
        analysis=_analysis(),
        conflict_strategy=None,
    )

    assert saved.original_filename.endswith(".docx")
    assert saved.display_name == "AI評分表審核系統_Python服務Running狀態檢測_簡短版"


def test_copy_strategy_creates_filename_copy(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(file_service, "DATA_ROOT", tmp_path)
    session = _session()
    teaching_class_id = uuid.uuid4()

    file_service.save_analyzed_file(
        session=session,
        teaching_class_id=teaching_class_id,
        uploaded_by=uuid.uuid4(),
        original_filename="rubric.pdf",
        file_hash="a" * 64,
        template_key="linux",
        file_bytes=b"one",
        analysis=_analysis("one"),
        conflict_strategy=None,
    )
    copy = file_service.save_analyzed_file(
        session=session,
        teaching_class_id=teaching_class_id,
        uploaded_by=uuid.uuid4(),
        original_filename="rubric.pdf",
        file_hash="b" * 64,
        template_key="linux",
        file_bytes=b"two",
        analysis=_analysis("two"),
        conflict_strategy="copy",
    )

    assert copy.original_filename == "rubric (2).pdf"
    assert copy.status == "active"
    assert (
        len(
            file_service.list_files(
                session=session, teaching_class_id=teaching_class_id
            )
        )
        == 2
    )


def test_save_file_write_failure_rolls_back_db(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(file_service, "DATA_ROOT", tmp_path)
    session = _session()
    teaching_class_id = uuid.uuid4()

    def fail_write_bytes(self, data):
        raise OSError("disk full")

    monkeypatch.setattr(file_service.Path, "write_bytes", fail_write_bytes)

    with pytest.raises(OSError):
        file_service.save_analyzed_file(
            session=session,
            teaching_class_id=teaching_class_id,
            uploaded_by=uuid.uuid4(),
            original_filename="rubric.pdf",
            file_hash="a" * 64,
            template_key="linux",
            file_bytes=b"one",
            analysis=_analysis("one"),
            conflict_strategy=None,
        )

    files = session.exec(select(TeacherJudgeFile)).all()
    assert files == []


def test_active_filename_unique_constraint_blocks_duplicate_active_files() -> None:
    session = _session()
    teaching_class_id = uuid.uuid4()
    session.add(
        TeacherJudgeFile(
            teaching_class_id=teaching_class_id,
            uploaded_by=uuid.uuid4(),
            original_filename="rubric.pdf",
            file_hash="a" * 64,
            template_key="linux",
            analysis_json=_analysis("one").model_dump(mode="json"),
            status=TeacherJudgeFileStatus.active,
        )
    )
    session.commit()
    session.add(
        TeacherJudgeFile(
            teaching_class_id=teaching_class_id,
            uploaded_by=uuid.uuid4(),
            original_filename="rubric.pdf",
            file_hash="b" * 64,
            template_key="linux",
            analysis_json=_analysis("two").model_dump(mode="json"),
            status=TeacherJudgeFileStatus.active,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_blank_file_has_created_source_metadata() -> None:
    session = _session()
    teaching_class_id = uuid.uuid4()

    file = file_service.create_blank_file(
        session=session,
        teaching_class_id=teaching_class_id,
        created_by=uuid.uuid4(),
        display_name="Python 期中評分表",
        environment_keys=["python", "linux", "python"],
    )


    session.commit()
    session.refresh(file)

    assert file.source_type == "created"
    assert file.original_filename is None
    assert file.file_hash is None
    assert file.display_name == "Python 期中評分表"
    assert file.environment_keys == ["python", "linux"]
    assert file.template_key == "python"
    assert file.analysis_revision == 1
    assert file.analysis_json["items"] == []


def test_upload_environment_keys_are_normalized_with_primary_first() -> None:
    assert _normalize_supported_environment_keys(
        ["python", "linux", "python"], "python"
    ) == ["python", "linux"]
    assert _normalize_supported_environment_keys(
        ["python", "linux"], "linux"
    ) == ["linux", "python"]
    assert _normalize_supported_environment_keys(None, "linux") == ["linux"]

    with pytest.raises(HTTPException) as exc_info:
        _normalize_supported_environment_keys(["unknown"], "linux")

    assert exc_info.value.status_code == 400


def test_blank_file_accepts_postgresql_environment() -> None:
    session = _session()
    file = file_service.create_blank_file(
        session=session,
        teaching_class_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        display_name="PostgreSQL 評分表",
        environment_keys=["postgresql"],
    )

    assert file.template_key == "postgresql"
    assert file.environment_keys == ["postgresql"]


def test_analysis_update_requires_current_revision() -> None:
    session = _session()
    teaching_class_id = uuid.uuid4()
    file = file_service.create_blank_file(
        session=session,
        teaching_class_id=teaching_class_id,
        created_by=uuid.uuid4(),
        display_name="Revision rubric",
        environment_keys=["linux"],
    )
    session.commit()
    session.refresh(file)

    changed_analysis = _analysis("first")
    changed_analysis.detectability_needs_review = True
    updated = file_service.update_file_analysis(
        session=session,
        teaching_class_id=teaching_class_id,
        file_id=file.id,
        analysis=changed_analysis,
        expected_revision=1,
    )
    assert updated.analysis_revision == 2
    assert updated.analysis_json["detectability_needs_review"] is True
    stored_before = session.get(TeacherJudgeFile, file.id)
    assert stored_before is not None
    before_json = stored_before.analysis_json

    with pytest.raises(HTTPException) as exc_info:
        file_service.update_file_analysis(
            session=session,
            teaching_class_id=teaching_class_id,
            file_id=file.id,
            analysis=_analysis("stale"),
            expected_revision=1,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "teacher_judge_analysis_revision_conflict"
    stored_after = session.get(TeacherJudgeFile, file.id)
    assert stored_after is not None
    assert stored_after.analysis_json == before_json


def test_metadata_update_keeps_effective_template_in_environment_set() -> None:
    session = _session()
    teaching_class_id = uuid.uuid4()
    file = file_service.create_blank_file(
        session=session,
        teaching_class_id=teaching_class_id,
        created_by=uuid.uuid4(),
        display_name="Metadata rubric",
        environment_keys=["linux", "python"],
    )
    session.commit()

    updated = file_service.update_file_metadata(
        session=session,
        teaching_class_id=teaching_class_id,
        file_id=file.id,
        payload=TeacherJudgeFileMetadataUpdateRequest(
            display_name="Updated rubric",
            environment_keys=["n8n", "python"],
            template_key="python",
        ),
    )

    assert updated.display_name == "Updated rubric"
    assert updated.environment_keys == ["n8n", "python"]
    assert updated.template_key == "python"


def test_uploaded_file_clone_copies_bytes_and_analysis_independently(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(file_service, "DATA_ROOT", tmp_path)
    session = _session()
    teaching_class_id = uuid.uuid4()
    source = file_service.save_analyzed_file(
        session=session,
        teaching_class_id=teaching_class_id,
        uploaded_by=uuid.uuid4(),
        original_filename="midterm.pdf",
        file_hash="a" * 64,
        template_key="linux",
        file_bytes=b"source bytes",
        analysis=_analysis("source"),
        conflict_strategy=None,
    )
    source_session = TeacherJudgeSession(
        teaching_class_id=teaching_class_id,
        title="Uploaded source",
        selected_file_id=uuid.UUID(source.id),
    )
    session.add(source_session)
    session.commit()
    session.refresh(source_session)

    cloned_session = session_service.fork_session_data(
        session,
        source_session,
        title="Uploaded copy",
        created_by=uuid.uuid4(),
    )
    cloned_file = session.get(TeacherJudgeFile, cloned_session.selected_file_id)
    assert cloned_file is not None
    assert cloned_file.id != uuid.UUID(source.id)
    assert cloned_file.original_filename == "midterm (2).pdf"
    assert (tmp_path / f"{cloned_file.id}.pdf").read_bytes() == b"source bytes"
    assert cloned_file.analysis_json == session.get(TeacherJudgeFile, uuid.UUID(source.id)).analysis_json


@pytest.mark.asyncio
async def test_overwrite_linked_file_marks_old_file_replaced_and_keeps_script(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(file_service, "DATA_ROOT", tmp_path)
    session = _session()
    teaching_class_id = uuid.uuid4()
    user_id = uuid.uuid4()

    async def fake_build_reviewed_script(*, rubric_snapshot, template_key):
        return (
            SAFE_SCRIPT,
            {"approved": True, "blocked": False, "risk_level": "low", "issues": []},
            {"approved": True, "risk_level": "low", "issues": []},
            TeacherJudgeScriptStatus.reviewed,
        )

    monkeypatch.setattr(
        script_artifact_service,
        "build_reviewed_script",
        fake_build_reviewed_script,
    )

    first = file_service.save_analyzed_file(
        session=session,
        teaching_class_id=teaching_class_id,
        uploaded_by=user_id,
        original_filename="rubric.pdf",
        file_hash="a" * 64,
        template_key="linux",
        file_bytes=b"one",
        analysis=_analysis("one"),
        conflict_strategy=None,
    )
    artifact = await script_artifact_service.create_artifact(
        session=session,
        teaching_class_id=teaching_class_id,
        name="rubric.pdf",
        template_key="linux",
        rubric_analysis=_analysis("one"),
        created_by=user_id,
        source_file_id=uuid.UUID(first.id),
    )
    second = file_service.save_analyzed_file(
        session=session,
        teaching_class_id=teaching_class_id,
        uploaded_by=user_id,
        original_filename="rubric.pdf",
        file_hash="b" * 64,
        template_key="linux",
        file_bytes=b"two",
        analysis=_analysis("two"),
        conflict_strategy="overwrite",
    )

    old_file = session.get(TeacherJudgeFile, uuid.UUID(first.id))
    active_files = session.exec(
        select(TeacherJudgeFile).where(
            TeacherJudgeFile.teaching_class_id == teaching_class_id,
            TeacherJudgeFile.status == TeacherJudgeFileStatus.active,
        )
    ).all()

    assert old_file is not None
    assert old_file.status == TeacherJudgeFileStatus.replaced
    assert second.id != first.id
    assert len(active_files) == 1
    assert active_files[0].id == uuid.UUID(second.id)
    assert artifact.source_file_id == first.id
    assert artifact.source_file_snapshot_json["original_filename"] == "rubric.pdf"


@pytest.mark.asyncio
async def test_delete_file_keeps_linked_script_with_snapshot(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(file_service, "DATA_ROOT", tmp_path)
    session = _session()
    teaching_class_id = uuid.uuid4()
    user_id = uuid.uuid4()

    async def fake_build_reviewed_script(*, rubric_snapshot, template_key):
        return (
            SAFE_SCRIPT,
            {"approved": True, "blocked": False, "risk_level": "low", "issues": []},
            {"approved": True, "risk_level": "low", "issues": []},
            TeacherJudgeScriptStatus.reviewed,
        )

    monkeypatch.setattr(
        script_artifact_service,
        "build_reviewed_script",
        fake_build_reviewed_script,
    )

    saved_file = file_service.save_analyzed_file(
        session=session,
        teaching_class_id=teaching_class_id,
        uploaded_by=user_id,
        original_filename="rubric.pdf",
        file_hash="a" * 64,
        template_key="linux",
        file_bytes=b"one",
        analysis=_analysis("one"),
        conflict_strategy=None,
    )
    artifact = await script_artifact_service.create_artifact(
        session=session,
        teaching_class_id=teaching_class_id,
        name="rubric.pdf",
        template_key="linux",
        rubric_analysis=_analysis("one"),
        created_by=user_id,
        source_file_id=uuid.UUID(saved_file.id),
    )

    file_service.delete_file(
        session=session,
        teaching_class_id=teaching_class_id,
        file_id=uuid.UUID(saved_file.id),
    )
    db_artifact = session.get(TeacherJudgeScriptArtifact, uuid.UUID(artifact.id))

    assert db_artifact is not None
    assert db_artifact.source_file_id is None
    assert db_artifact.script_content == SAFE_SCRIPT
    assert db_artifact.source_file_snapshot_json["original_filename"] == "rubric.pdf"


def test_delete_file_clears_session_source_reference_and_bytes(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(file_service, "DATA_ROOT", tmp_path)
    session = _session()
    teaching_class_id = uuid.uuid4()
    saved_file = file_service.save_analyzed_file(
        session=session,
        teaching_class_id=teaching_class_id,
        uploaded_by=uuid.uuid4(),
        original_filename="rubric.pdf",
        file_hash="a" * 64,
        template_key="linux",
        file_bytes=b"source bytes",
        analysis=_analysis(),
        conflict_strategy=None,
    )
    owner = TeacherJudgeSession(
        teaching_class_id=teaching_class_id,
        title="Owns source",
        selected_file_id=uuid.UUID(saved_file.id),
    )
    session.add(owner)
    session.commit()

    stored_path = tmp_path / f"{saved_file.id}.pdf"
    assert stored_path.read_bytes() == b"source bytes"

    file_service.delete_file(
        session=session,
        teaching_class_id=teaching_class_id,
        file_id=uuid.UUID(saved_file.id),
    )

    assert session.get(TeacherJudgeFile, uuid.UUID(saved_file.id)) is None
    refreshed_owner = session.get(TeacherJudgeSession, owner.id)
    assert refreshed_owner is not None
    assert refreshed_owner.selected_file_id is None
    assert not stored_path.exists()
