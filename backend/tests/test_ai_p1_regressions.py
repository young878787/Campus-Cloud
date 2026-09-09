"""Isolated regressions for the backend AI P1 review findings."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from proxmoxer.core import ResourceException
from sqlmodel import Session, SQLModel, create_engine

from app.ai.navigation.service import _extract_first_json_object
from app.ai.pve_log import collector
from app.ai.pve_log.chat import _execute_tool_sync
from app.ai.system_config import system_ai_env
from app.ai.teacher_judge import script_artifact_service as artifacts
from app.ai.teacher_judge import script_executor_service as executor
from app.ai.teacher_judge import script_result_analysis_service as analysis
from app.ai.teacher_judge import service
from app.ai.teacher_judge.prompt import CHAT_SYSTEM_TEMPLATE
from app.ai.teacher_judge.schemas import TeacherJudgeRubricChatMessage
from app.models.teacher_judge_script_artifact import (
    TeacherJudgeScriptArtifact,
    TeacherJudgeScriptStatus,
)
from app.models.teacher_judge_script_run import (
    TeacherJudgeScriptRun,
    TeacherJudgeScriptRunStatus,
)


@pytest.mark.parametrize("value", ["a } brace", "a { brace", 'escaped \\" quote { }'])
def test_navigation_json_handles_braces_inside_strings(value):
    expected = {"intent": value, "action": "clarify"}
    text = "```json\n" + json.dumps(expected) + "\n```"
    assert json.loads(_extract_first_json_object(text)) == expected


@pytest.mark.parametrize(
    "prompt", [CHAT_SYSTEM_TEMPLATE, artifacts.AI_REVIEWER_SYSTEM_PROMPT]
)
def test_plain_prompt_json_examples_are_valid(prompt):
    assert "\n{{\n" not in prompt
    start = prompt.index("{\n")
    json.JSONDecoder().raw_decode(prompt[start:])


def test_teacher_judge_prompt_exposes_script_workflow_intent_rules():
    assert "request_check_script_creation" in CHAT_SYSTEM_TEMPLATE
    assert "可以幫我產生腳本嗎" in CHAT_SYSTEM_TEMPLATE
    assert "腳本怎麼製作" in CHAT_SYSTEM_TEMPLATE
    assert "不要用 JSON 文字模擬工具呼叫" in CHAT_SYSTEM_TEMPLATE


@pytest.mark.parametrize("content", ["null", "[]", '"text"'])
async def test_non_object_rubric_and_script_outputs_fail_cleanly(monkeypatch, content):
    monkeypatch.setattr(system_ai_env, "vllm_model_name", "test-model")

    async def fake_call(*args, **kwargs):
        return content, {}

    monkeypatch.setattr(service, "_call_vllm", fake_call)
    monkeypatch.setattr(artifacts, "_call_vllm", fake_call)
    with pytest.raises(HTTPException) as error:
        await service.analyze_rubric("rubric")
    assert error.value.status_code == 502
    with pytest.raises(HTTPException) as error:
        await artifacts.fix_script_content(script_content="pass", fix_hints=[])
    assert error.value.status_code == 502
    with pytest.raises(HTTPException) as error:
        await artifacts.generate_script_content(
            rubric_snapshot={}, template_key="linux"
        )
    assert error.value.status_code == 502
    reply, proposal, _ = await service.chat_with_rubric(
        [TeacherJudgeRubricChatMessage(role="user", content="說明")], "{}"
    )
    assert reply == content
    assert proposal is None


@pytest.mark.asyncio
async def test_teacher_judge_chat_preserves_create_script_tool_call(monkeypatch):
    monkeypatch.setattr(system_ai_env, "vllm_model_name", "test-model")
    captured = {}

    async def fake_call(payload, timeout=60.0):
        captured["payload"] = payload
        return service.VLLMCallResult(
            content="",
            metrics={},
            message={
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-create-script",
                        "type": "function",
                        "function": {
                            "name": "request_check_script_creation",
                            "arguments": "{}",
                        },
                    }
                ],
            },
        )

    monkeypatch.setattr(service, "_call_vllm", fake_call)
    reply, proposal, metrics = await service.chat_with_rubric(
        [
            TeacherJudgeRubricChatMessage(
                role="user", content="可以幫我製作檢查腳本嗎"
            )
        ],
        '{"items":[{"id":"item-1"}]}',
        enable_workflow_tools=True,
    )

    assert "製作檢查腳本" in reply
    assert proposal is None
    assert metrics["workflow_action"] == {
        "type": "create_script",
        "status": "requested",
        "tool_call_id": "call-create-script",
    }
    assert captured["payload"]["tools"][0]["function"]["name"] == (
        "request_check_script_creation"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content, expected_action",
    [
        ("可以幫我製作檢查腳本嗎", True),
        ("幫我做檢查腳本", True),
        ("請說明如何製作檢查腳本", False),
        ("腳本安全嗎？", False),
        ("沒問題，我現在就為您啟動檢查腳本的製作流程，請稍候。", False),
        ("how to create check script", False),
    ],
)
async def test_teacher_judge_chat_falls_back_to_explicit_user_intent(
    monkeypatch, content, expected_action
):
    """A prose-only model reply must not hide an explicit script command."""

    monkeypatch.setattr(system_ai_env, "vllm_model_name", "test-model")

    async def fake_call(payload, timeout=60.0):
        return (
            json.dumps(
                {
                    "reply": "沒問題，我現在就為您啟動檢查腳本的製作流程，請稍候。",
                    "updated_items": None,
                },
                ensure_ascii=False,
            ),
            {},
        )

    monkeypatch.setattr(service, "_call_vllm", fake_call)
    _reply, _proposal, metrics = await service.chat_with_rubric(
        [TeacherJudgeRubricChatMessage(role="user", content=content)],
        '{"items":[{"id":"item-1"}]}',
        enable_workflow_tools=True,
    )

    assert ("workflow_action" in metrics) is expected_action


async def test_teacher_judge_summary_uses_dedicated_low_budget_prompt(monkeypatch):
    monkeypatch.setattr(system_ai_env, "vllm_model_name", "test-model")
    captured = {}

    async def fake_call(payload, timeout=60.0):
        captured["payload"] = payload
        captured["timeout"] = timeout
        return "  已確認只保留 Python 檢查。  ", {}

    monkeypatch.setattr(service, "_call_vllm", fake_call)
    summary, metrics = await service.summarize_conversation(
        [
            TeacherJudgeRubricChatMessage(role="user", content="保留 Python 檢查"),
            TeacherJudgeRubricChatMessage(role="assistant", content="好的"),
        ],
        previous_summary="舊方向",
    )

    payload = captured["payload"]
    assert summary == "已確認只保留 Python 檢查。"
    assert metrics == {}
    assert payload["max_tokens"] <= 768
    assert "response_format" not in payload
    assert "不要新增、刪除或修改任何評分項目" in payload["messages"][0]["content"]
    assert "舊方向" in payload["messages"][1]["content"]
    assert payload["messages"][-1]["role"] == "user"


async def test_truncated_model_output_is_not_accepted_as_complete_json(monkeypatch):
    async def fake_completion(*args, **kwargs):
        return {
            "choices": [
                {"finish_reason": "length", "message": {"content": '{"items": []}'}}
            ]
        }

    monkeypatch.setattr(
        service.teacher_judge_client, "create_chat_completion", fake_completion
    )
    with pytest.raises(HTTPException) as error:
        await service._call_vllm({"response_format": {"type": "json_object"}})
    assert error.value.status_code == 502


def _fake_pve(monkeypatch, cluster_get):
    proxmox = SimpleNamespace(
        cluster=SimpleNamespace(
            status=SimpleNamespace(get=cluster_get),
            resources=SimpleNamespace(get=lambda **kwargs: []),
        ),
        nodes=SimpleNamespace(get=lambda: []),
    )
    monkeypatch.setattr(collector, "get_proxmox_api", lambda: proxmox)
    monkeypatch.setattr(collector.settings, "collector_retry_attempts", 3)
    monkeypatch.setattr(collector.settings, "collector_retry_backoff", 0)
    return proxmox


def test_collector_retries_before_returning_partial_snapshot(monkeypatch):
    calls = []

    def unavailable():
        calls.append(1)
        raise OSError("synthetic unavailable")

    _fake_pve(monkeypatch, unavailable)
    snapshot = collector.collect_snapshot()
    assert len(calls) == 3
    assert snapshot.cluster.quorate is False
    assert snapshot.errors
    tool = _execute_tool_sync(snapshot, "get_cluster", {})
    assert tool.get("error")
    assert tool["quorate"] is False


def test_collector_transient_cluster_failure_recovers(monkeypatch):
    calls = []

    def recover():
        calls.append(1)
        if len(calls) == 1:
            raise OSError("temporary")
        return [{"type": "cluster", "name": "test", "nodes": 2, "quorate": 1}]

    _fake_pve(monkeypatch, recover)
    snapshot = collector.collect_snapshot()
    assert len(calls) == 2
    assert snapshot.cluster.quorate is True
    assert snapshot.errors == []


@pytest.mark.parametrize(
    "fetch,args",
    [
        ("_collect_storages_for_node", ("node",)),
        ("_collect_resource_status", ("node", 1, "qemu")),
        ("_collect_resource_config", ("node", 1, "qemu")),
        ("_collect_lxc_interfaces", ("node", 1)),
    ],
)
def test_collector_fetch_errors_reach_retry_layer(fetch, args):
    def unavailable(*args):
        raise OSError("synthetic unavailable")

    with pytest.raises(OSError):
        getattr(collector, fetch)(SimpleNamespace(nodes=unavailable), *args)


@pytest.mark.parametrize(
    "status,expected_calls", [(401, 1), (403, 1), (404, 1), (429, 3), (503, 3)]
)
def test_collector_retries_only_transient_http_failures(
    monkeypatch, status, expected_calls
):
    calls = []

    def unavailable():
        calls.append(1)
        raise ResourceException(status, "synthetic", "unavailable")

    _fake_pve(monkeypatch, unavailable)
    snapshot = collector.collect_snapshot()
    assert len(calls) == expected_calls
    assert snapshot.errors


async def test_cancelled_analysis_waiter_does_not_consume_released_slot(monkeypatch):
    slots = threading.BoundedSemaphore(1)
    slots.acquire()
    monkeypatch.setattr(analysis, "_AI_ANALYSIS_SLOTS", slots)
    task = asyncio.create_task(analysis._acquire_ai_slot())
    try:
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        slots.release()
        await asyncio.sleep(0.05)
        acquired = slots.acquire(blocking=False)
        assert acquired
    finally:
        # Also unblock the old implementation's worker after a regression failure.
        slots.release()


def test_rubric_excerpt_preserves_items_after_twenty_and_partial_id_matches():
    items = [{"id": f"item-{i}", "title": f"題目 {i}"} for i in range(25)]
    result = analysis._rubric_excerpt({"items": items})
    assert [item["id"] for item in result] == [item["id"] for item in items]


def _judgement():
    return {
        "score": 5,
        "max_score": 5,
        "summary": "符合要求",
        "item_judgements": [
            {
                "item_id": "item-1",
                "title": "服務",
                "status": "pass",
                "score": 1,
                "max_score": 1,
                "evidence_refs": ["service.http"],
                "comment": "回應正常",
            }
        ],
    }


def _analysis_payload():
    return {
        "rubric_items": [{"id": "item-1", "title": "服務"}],
        "script_result": {"checks": [{"id": "service.http", "status": "pass"}]},
    }


@pytest.mark.parametrize(
    "invalid", ["empty", "item", "ref", "status", "no_refs", "unknown_evidence"]
)
async def test_invalid_judgements_are_rejected(monkeypatch, invalid):
    monkeypatch.setattr(system_ai_env, "vllm_model_name", "test-model")
    judgement = _judgement()
    payload = _analysis_payload()
    item = judgement["item_judgements"][0]
    if invalid == "empty":
        judgement = {}
    elif invalid == "item":
        item["item_id"] = "nonexistent"
    elif invalid == "ref":
        item["evidence_refs"] = ["nonexistent"]
    elif invalid == "status":
        item["status"] = "perfect"
    elif invalid == "no_refs":
        item["evidence_refs"] = []
    else:
        payload["script_result"]["checks"][0]["status"] = "unknown"

    async def fake_call(*args, **kwargs):
        return json.dumps(judgement), {}

    monkeypatch.setattr(analysis, "_call_vllm", fake_call)
    with pytest.raises(HTTPException) as error:
        await analysis._call_ai_judgement(payload)
    assert error.value.status_code == 502


async def test_valid_judgement_accepts_different_rubric_and_check_ids(monkeypatch):
    monkeypatch.setattr(system_ai_env, "vllm_model_name", "test-model")

    async def fake_call(*args, **kwargs):
        return json.dumps(_judgement()), {}

    monkeypatch.setattr(analysis, "_call_vllm", fake_call)
    result = await analysis._call_ai_judgement(_analysis_payload())
    assert result["score"] == 5
    assert result["item_judgements"][0]["evidence_refs"] == ["service.http"]


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"approved": True, "risk_level": "invalid", "issues": []},
        {"approved": "true", "risk_level": "low", "issues": []},
        {"approved": True, "risk_level": "low", "issues": ["unsafe"]},
    ],
)
def test_reviewer_invalid_or_contradictory_output_never_approves(payload):
    assert artifacts._normalize_ai_review(payload)["approved"] is False


@pytest.mark.parametrize("status", ["unknown", "skipped"])
async def test_unknown_judgement_preserves_status_without_fabricated_refs(
    monkeypatch, status
):
    monkeypatch.setattr(system_ai_env, "vllm_model_name", "test-model")
    result = _judgement()
    result["score"] = 0
    result["item_judgements"][0].update(status=status, score=0, evidence_refs=[])

    async def fake_call(*args, **kwargs):
        return json.dumps(result), {}

    monkeypatch.setattr(analysis, "_call_vllm", fake_call)
    judgement = await analysis._call_ai_judgement(_analysis_payload())
    assert judgement["item_judgements"][0]["status"] == status


async def test_judgement_cannot_silently_omit_rubric_items(monkeypatch):
    monkeypatch.setattr(system_ai_env, "vllm_model_name", "test-model")
    payload = _analysis_payload()
    payload["rubric_items"].append({"id": "item-2", "title": "another item"})

    async def fake_call(*args, **kwargs):
        return json.dumps(_judgement()), {}

    monkeypatch.setattr(analysis, "_call_vllm", fake_call)
    with pytest.raises(HTTPException):
        await analysis._call_ai_judgement(payload)


async def test_analysis_slot_released_after_http_failure(monkeypatch):
    monkeypatch.setattr(system_ai_env, "vllm_model_name", "test-model")
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(analysis, "_AI_ANALYSIS_SLOTS", slots)

    async def unavailable(*args, **kwargs):
        raise HTTPException(status_code=504, detail="synthetic timeout")

    monkeypatch.setattr(analysis, "_call_vllm", unavailable)
    with pytest.raises(HTTPException):
        await analysis._call_ai_judgement(_analysis_payload())
    assert slots.acquire(blocking=False)
    slots.release()


async def test_executor_sync_stage_does_not_block_loop(monkeypatch):
    entered = threading.Event()
    released = threading.Event()
    loop_thread = threading.get_ident()
    worker_threads = []

    def unexpected_load(**kwargs):
        raise AssertionError("Synchronous execution must run in the worker stage")

    monkeypatch.setattr(executor, "_load_run_and_artifact", unexpected_load)

    def execute_targets(run_id):
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
        await task


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

    def execute_targets(run_id):
        if stage == "execute":
            block()
        return executor._ExecutedTargets({}, {}, [])

    def save(run_id, results):
        assert stage == "save"
        block()

    async def analyze(**kwargs):
        return []

    monkeypatch.setattr(executor, "_execute_targets", execute_targets)
    monkeypatch.setattr(executor, "analyze_target_results", analyze)
    monkeypatch.setattr(executor, "_save_analyzed_results", save)
    monkeypatch.setattr(
        executor, "_mark_run_executor_failed", lambda *args: events.append("failed")
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
            await task
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
            teaching_class_id=artifact.teaching_class_id,
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

    async def fake_analysis(**kwargs):
        assert threading.get_ident() == loop_thread
        return kwargs["target_results"]

    monkeypatch.setattr(executor, "engine", db_engine)
    monkeypatch.setattr(executor, "Session", owned_session)
    monkeypatch.setattr(executor, "_live_running_by_vmid", lambda: {})
    monkeypatch.setattr(
        executor, "_resolve_runtime_target", lambda **kwargs: dict(kwargs["target"])
    )
    monkeypatch.setattr(executor, "_execute_target_script", fake_ssh)
    monkeypatch.setattr(executor, "analyze_target_results", fake_analysis)
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
        await task
    assert session_threads and loop_thread not in session_threads
    with Session(db_engine) as session:
        stored = session.get(TeacherJudgeScriptRun, run_id)
        assert stored.status == TeacherJudgeScriptRunStatus.completed
        assert stored.target_results_json["targets"][0]["vmid"] == 101
    # A late cancellation/failure cannot overwrite a committed completion.
    await asyncio.to_thread(executor._mark_run_executor_failed, run_id, "late failure")
    with Session(db_engine) as session:
        assert (
            session.get(TeacherJudgeScriptRun, run_id).status
            == TeacherJudgeScriptRunStatus.completed
        )
    db_engine.dispose()
