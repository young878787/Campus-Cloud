"""Deterministic typed Check Plan compiler and v2 result contracts."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid

import pytest
from sqlmodel import Session

from app.ai.teacher_judge import script_artifact_service
from app.ai.teacher_judge.deterministic_compiler import (
    compile_check_plan,
    is_typed_plan,
    validate_check_plan,
)
from app.ai.teacher_judge.schemas import (
    TeacherJudgeRubricAnalysis,
    TeacherJudgeRubricCheckStep,
    TeacherJudgeRubricItem,
)
from app.ai.teacher_judge.script_policy import validate_managed_script_output
from app.ai.teacher_judge.script_run_service import project_run_items
from app.models.teacher_judge_script_artifact import (
    TeacherJudgeScriptArtifact,
    TeacherJudgeScriptLanguage,
    TeacherJudgeScriptStatus,
)
from app.models.teaching_class import TeachingClassMachineNode
from tests.ai.teacher_judge.helpers import make_session


def _typed_item(
    *,
    mode: str = "system",
    node_key: str = "web",
    peer_node_key: str | None = None,
) -> TeacherJudgeRubricItem:
    collector: dict[str, object]
    if peer_node_key:
        collector = {"type": "peer_ping", "timeout_seconds": 5}
    else:
        collector = {"type": "file_stat", "path": "answer.txt"}
    assertion = (
        None if mode == "teacher" else {"type": "exists", "expected": True}
    )
    step = TeacherJudgeRubricCheckStep.model_validate(
        {
            "id": "answer.exists",
            "title": "答案檔案存在",
            "collector": collector,
            "assertion": assertion,
        }
    )
    return TeacherJudgeRubricItem(
        id="answer",
        title="答案檔案",
        detectable="auto",
        judgement_mode=mode,
        detection_method="檢查答案檔案",
        target_node_key=node_key,
        peer_node_key=peer_node_key,
        check_steps=[step],
    )


def test_typed_plan_is_valid_and_legacy_ai_is_normalized() -> None:
    item = _typed_item()
    snapshot = {"items": [item.model_dump(mode="json")]}

    assert is_typed_plan(snapshot) is True
    validation = validate_check_plan(snapshot)

    assert validation["approved"] is True
    assert validation["plan"]["schema_version"] == "teacher_judge_check_plan.v1"
    assert validation["plan"]["items"][0]["judgement_mode"] == "system"
    assert validation["mappings"] == [
        {"check_id": "answer.exists", "rubric_item_ids": ["answer"]}
    ]


def test_typed_plan_rejects_dangerous_command_and_same_peer() -> None:
    dangerous = _typed_item().model_dump(mode="json")
    dangerous["check_steps"][0] = {
        "id": "bad",
        "collector": {
            "type": "command",
            "argv": ["rm", "-rf", "/tmp"],
            "timeout_seconds": 5,
        },
        "assertion": {"type": "returncode_equals", "expected": 0},
    }
    dangerous["peer_node_key"] = "web"
    validation = validate_check_plan({"items": [dangerous]})

    assert validation["approved"] is False
    messages = " ".join(issue["message"] for issue in validation["issues"])
    assert "禁止" in messages
    assert "不得等於" in messages


def test_compiled_runtime_emits_v2_and_executes_without_model(tmp_path) -> None:
    item = _typed_item(mode="teacher")
    script, policy = compile_check_plan(
        {"items": [item.model_dump(mode="json")]}
    )
    assert policy["compiler"] == "teacher_judge_compiler.v1"
    assert script == compile_check_plan(
        {"items": [item.model_dump(mode="json")]}
    )[0]

    (tmp_path / "answer.txt").write_text("OK\n", encoding="utf-8")
    (tmp_path / "runtime_context.json").write_text(
        json.dumps({"peers": {}}, ensure_ascii=False), encoding="utf-8"
    )
    script_path = tmp_path / "script.py"
    script_path.write_text(script, encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["schema_version"] == "teacher_judge_result.v2"
    assert result["checks"][0]["status"] == "collected"
    assert result["checks"][0]["judgement_mode"] == "teacher"
    assert validate_managed_script_output(completed.stdout)["valid"] is True


def test_teacher_collected_result_projects_as_reviewable() -> None:
    item = _typed_item(mode="teacher")
    artifact = TeacherJudgeScriptArtifact(
        teaching_class_id=uuid.uuid4(),
        target_node_key="web",
        rubric_snapshot_json={"items": [item.model_dump(mode="json")]},
        policy_check_result_json={
            "coverage": {
                "mappings": [
                    {"check_id": "answer.exists", "rubric_item_ids": ["answer"]}
                ]
            }
        },
        script_language=TeacherJudgeScriptLanguage.python,
        script_content="",
        status=TeacherJudgeScriptStatus.approved,
        name="web",
        template_key="linux",
    )
    projected = project_run_items(
        artifact=artifact,
        target_result={
            "status": "completed",
            "parsed_result": {
                "schema_version": "teacher_judge_result.v2",
                "checks": [
                    {
                        "id": "answer.exists",
                        "title": "答案檔案存在",
                        "status": "collected",
                        "evidence": {"summary": "已收集"},
                    }
                ],
            },
        },
        display_labels={"web": "P1"},
    )

    assert projected["items"][0]["status"] == "collected"
    assert projected["items"][0]["judgement_mode"] == "teacher"


@pytest.mark.asyncio
async def test_typed_artifact_set_bypasses_per_node_ai_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session: Session = make_session()
    class_id = uuid.uuid4()
    session.add(
        TeachingClassMachineNode(
            class_id=class_id,
            node_key="web",
            name="Web",
            role="frontend",
            resource_type="lxc",
            cpu=1,
            memory_mb=512,
            disk_gb=8,
            sort_order=0,
        )
    )
    session.commit()

    async def unexpected_ai_build(**_kwargs: object) -> object:
        raise AssertionError("typed Check Plan must not call vLLM script generation")

    monkeypatch.setattr(
        script_artifact_service,
        "_build_reviewed_script_for_artifact",
        unexpected_ai_build,
    )
    analysis = TeacherJudgeRubricAnalysis(
        items=[_typed_item()],
        total_items=1,
        auto_count=1,
    )

    result = await script_artifact_service.create_artifact_set(
        session=session,
        teaching_class_id=class_id,
        session_id=uuid.uuid4(),
        name="typed plan",
        template_key="linux",
        rubric_analysis=analysis,
        source_analysis_revision=1,
        created_by=None,
        source_file_id=None,
    )

    assert result.status == "approved"
    assert len(result.children) == 1
    assert result.children[0].policy_check_result_json["source"] == (
        "deterministic_compiler"
    )
    assert "teacher_judge_result.v2" in result.children[0].script_content
