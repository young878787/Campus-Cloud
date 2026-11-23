"""app/ai/teacher_judge/script_executor_service.py 的執行緒與事件迴圈：同步執行、DB session 與 SSH 等待都不得阻塞事件迴圈；取消時須先排空 worker 再記錄失敗。"""

from __future__ import annotations

import asyncio
import json
import threading
import uuid

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.ai.teacher_judge import script_executor_service as executor
from app.models.teacher_judge_script_artifact import (
    TeacherJudgeScriptArtifact,
    TeacherJudgeScriptStatus,
)
from app.models.teacher_judge_script_run import (
    TeacherJudgeScriptRun,
    TeacherJudgeScriptRunStatus,
)


async def test_executor_sync_stage_does_not_block_loop(monkeypatch):
    entered = threading.Event()
    released = threading.Event()
    loop_thread = threading.get_ident()
    worker_threads = []

    def unexpected_load(**kwargs):
        raise AssertionError("Synchronous execution must run in the worker stage")

    monkeypatch.setattr(executor, "_load_run_and_artifact", unexpected_load)

    def execute_targets(run_id, *, stop_event=None):
        worker_threads.append(threading.get_ident())
        entered.set()
        assert released.wait(2)
        return None

    monkeypatch.setattr(executor, "_execute_targets", execute_targets, raising=False)
    task = asyncio.create_task(executor._execute_script_run(uuid.uuid4()))
    try:
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(0.005)
        assert entered.is_set()
        assert len(worker_threads) == 1
        assert worker_threads[0] != loop_thread
    finally:
        released.set()
        _ = await task


@pytest.mark.parametrize("stage", ["execute", "save"])
async def test_executor_cancellation_drains_worker_before_recording_failure(
    monkeypatch, stage
):
    entered = threading.Event()
    released = threading.Event()
    events = []

    def block():
        entered.set()
        assert released.wait(2)
        events.append("worker_finished")

    def execute_targets(run_id, *, stop_event=None):
        if stage == "execute":
            block()
        return executor._ExecutedTargets([])

    def save(run_id, results):
        assert stage == "save"
        block()

    monkeypatch.setattr(executor, "_execute_targets", execute_targets)
    monkeypatch.setattr(executor, "_save_results", save)
    monkeypatch.setattr(
        executor,
        "_mark_run_executor_failed",
        lambda *args, **kwargs: events.append("failed"),
    )
    task = asyncio.create_task(executor.execute_script_run(uuid.uuid4()))
    try:
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(0.005)
        assert entered.is_set()
        task.cancel()
        await asyncio.sleep(0.02)
        task.cancel()
        await asyncio.sleep(0.02)
        assert not task.done()
        assert events == []
    finally:
        released.set()
        with pytest.raises(asyncio.CancelledError):
            _ = await task
    assert events == ["worker_finished", "failed"]


async def test_executor_sessions_and_ssh_wait_stay_off_loop(monkeypatch, tmp_path):
    db_engine = create_engine(f"sqlite:///{tmp_path / 'executor.sqlite'}")
    SQLModel.metadata.create_all(db_engine)
    with Session(db_engine) as session:
        artifact = TeacherJudgeScriptArtifact(
            teaching_class_id=uuid.uuid4(),
            name="test",
            template_key="linux",
            rubric_snapshot_json={},
            script_content="pass",
            status=TeacherJudgeScriptStatus.approved,
        )
        session.add(artifact)
        session.flush()
        run = TeacherJudgeScriptRun(
            artifact_id=artifact.id,
            target_snapshot_json={"targets": [{"vmid": 101}]},
        )
        session.add(run)
        session.commit()
        run_id = run.id

    entered = threading.Event()
    released = threading.Event()
    loop_thread = threading.get_ident()
    session_threads = []

    def owned_session(*args, **kwargs):
        session_threads.append(threading.get_ident())
        return Session(*args, **kwargs)

    def fake_ssh(**kwargs):
        entered.set()
        assert released.wait(2)
        return executor.RemoteScriptResult(
            0,
            json.dumps(
                {
                    "schema_version": "teacher_judge_result.v1",
                    "metadata": {
                        "timestamp": "2026-09-07T00:00:00Z",
                        "platform": "linux",
                    },
                    "summary": "done",
                    "checks": [],
                    "errors": [],
                }
            ),
            "",
        )

    monkeypatch.setattr(executor, "engine", db_engine)
    monkeypatch.setattr(executor, "Session", owned_session)
    monkeypatch.setattr(executor, "_live_running_by_vmid", lambda: {})
    monkeypatch.setattr(
        executor, "_resolve_runtime_target", lambda **kwargs: dict(kwargs["target"])
    )
    monkeypatch.setattr(executor, "_execute_target_script", fake_ssh)
    task = asyncio.create_task(executor.execute_script_run(run_id))
    try:
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(0.005)
        assert entered.is_set()
        assert not task.done()
    finally:
        released.set()
        _ = await task
    assert session_threads and loop_thread not in session_threads
    with Session(db_engine) as session:
        stored = session.get(TeacherJudgeScriptRun, run_id)
        assert stored.status == TeacherJudgeScriptRunStatus.completed
        assert stored.results_document["targets"][0]["vmid"] == 101
    # A late cancellation/failure cannot overwrite a committed completion.
    await asyncio.to_thread(executor._mark_run_executor_failed, run_id, "late failure")
    with Session(db_engine) as session:
        assert (
            session.get(TeacherJudgeScriptRun, run_id).status
            == TeacherJudgeScriptRunStatus.completed
        )
    db_engine.dispose()
