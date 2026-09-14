"""Phase 0 characterization baseline for the session chat workflow convergence.

Each test pins the current (2026-09-13) observable behavior of
``chat_with_rubric`` — reply/proposal/status and the number of LLM calls —
so Phase 1-3 refactors can prove behavior equivalence and Phase 3 can compare
token budgets.  See docs/chen_yang/2026-09-13-teacher-judge-chat-workflow-convergence-plan.md.
"""

from __future__ import annotations

import json

import pytest

from app.ai.system_config import system_ai_env
from app.ai.teacher_judge import service
from app.ai.teacher_judge.schemas import TeacherJudgeRubricChatMessage
from app.models.teacher_judge_template_command import TeacherJudgeTemplateCommand


def _general_command() -> TeacherJudgeTemplateCommand:
    return TeacherJudgeTemplateCommand(
        template_key="linux",
        command_key="system.run_command",
        command_label="通用受控指令",
        category="inspection",
        command_template="argv + cwd + timeout",
        description="執行單一唯讀診斷指令。",
        risk_level="executes_command",
        requires_confirmation=True,
    )


def _ready_item(item_id: str, title: str, argv: list[str]) -> dict:
    return {
        "id": item_id,
        "title": title,
        "description": f"{title}（自動比對）",
        "detectable": "auto",
        "detection_method": "比較 exit code 與 stdout。",
        "check_steps": [
            {
                "template_key": "linux",
                "command_key": "system.run_command",
                "parameters": {
                    "argv": argv,
                    "cwd": "/home/student/project",
                    "timeout_seconds": 30,
                    "success_criteria": "exit code 為 0",
                },
            }
        ],
    }


def _port_gap_item() -> dict:
    return {
        "id": "item-port",
        "title": "Web 服務回傳 200",
        "description": "檢查 Web 服務。",
        "detectable": "partial",
        "detection_method": "發送 HTTP request。",
        "missing_information": ["服務 Port"],
        "check_steps": [],
    }


class _CallRecorder:
    def __init__(self) -> None:
        self.payloads: list[dict] = []
        self.responses: list[str] = []

    def queue(self, response: dict | str) -> None:
        self.responses.append(
            response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)
        )

    async def __call__(self, payload: dict, timeout: float = 60.0):
        index = min(len(self.payloads), len(self.responses) - 1)
        self.payloads.append(payload)
        return self.responses[index], {"prompt_tokens": 10, "completion_tokens": 10}


@pytest.mark.asyncio
async def test_baseline_single_ready_item_uses_one_call(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(system_ai_env, "vllm_model_name", "test-model")
    recorder = _CallRecorder()
    recorder.queue(
        {
            "reply": "已把需求整理成提案。",
            "proposal_status": "ready",
            "updated_items": [
                _ready_item("item-a", "檢查 Python 版本", ["python3", "--version"])
            ],
        }
    )
    monkeypatch.setattr(service, "_call_vllm_message", recorder)

    result = await service.chat_with_rubric(
        [TeacherJudgeRubricChatMessage(role="user", content="檢查 Python 版本")],
        json.dumps({"items": []}, ensure_ascii=False),
        template_commands=[_general_command()],
    )

    reply, proposal, _ = result
    assert len(recorder.payloads) == 1
    assert proposal is not None and len(proposal) == 1
    assert proposal[0]["operation"] == "add"
    assert "提案" in reply


@pytest.mark.asyncio
async def test_baseline_partial_item_asks_once_without_proposal(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(system_ai_env, "vllm_model_name", "test-model")
    recorder = _CallRecorder()
    recorder.queue(
        {
            "reply": "請補充服務要檢查的 Port。",
            "proposal_status": "needs_information",
            "updated_items": None,
            "conversation_focus": {
                "turn_kind": "requirement",
                "requirements": [
                    {
                        "focus_key": "web-port",
                        "status": "needs_information",
                        "known_information": ["檢查 Web 服務"],
                        "missing_information": ["服務 Port"],
                    }
                ],
            },
        }
    )
    monkeypatch.setattr(service, "_call_vllm_message", recorder)

    result = await service.chat_with_rubric(
        [TeacherJudgeRubricChatMessage(role="user", content="檢查 Web 服務")],
        json.dumps({"items": []}, ensure_ascii=False),
        template_commands=[_general_command()],
    )

    reply, proposal, _ = result
    assert len(recorder.payloads) == 1
    assert proposal is None
    assert "Port" in reply


@pytest.mark.asyncio
async def test_baseline_mixed_requirements_keep_ready_subset_only(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(system_ai_env, "vllm_model_name", "test-model")
    recorder = _CallRecorder()
    recorder.queue(
        {
            "reply": "1. Python 版本 Ready。2. Web 服務缺少 Port。",
            "proposal_status": "ready",
            "updated_items": [
                _ready_item("item-ready", "檢查 Python 版本", ["python3", "--version"]),
                _port_gap_item(),
            ],
        }
    )
    monkeypatch.setattr(service, "_call_vllm_message", recorder)

    result = await service.chat_with_rubric(
        [
            TeacherJudgeRubricChatMessage(
                role="user", content="檢查 Python 版本；檢查 Web 服務"
            )
        ],
        json.dumps({"items": []}, ensure_ascii=False),
        template_commands=[_general_command()],
    )

    reply, proposal, _ = result
    assert len(recorder.payloads) == 1
    assert proposal is not None
    assert [item["id"] for item in proposal] == ["item-ready"]
    assert "Port" in reply
    assert [row["status"] for row in result.item_statuses] == [
        "ready",
        "needs_information",
    ]
    assert result.item_statuses[0]["operation"]["id"] == "item-ready"
    assert result.item_statuses[1]["operation"] is None
    assert result.item_statuses[1]["missing_information"] == ["服務 Port"]


@pytest.mark.asyncio
async def test_mixed_requirements_reply_lists_each_unresolved_gap(
    monkeypatch: pytest.MonkeyPatch,
):
    """A terse model reply cannot hide the missing field of one candidate."""
    monkeypatch.setattr(system_ai_env, "vllm_model_name", "test-model")
    recorder = _CallRecorder()
    recorder.queue(
        {
            "reply": "已整理可用的檢查項目。",
            "proposal_status": "ready",
            "updated_items": [
                _ready_item("item-ready", "檢查 Python 版本", ["python3", "--version"]),
                {
                    **_port_gap_item(),
                    "missing_information": ["服務 Port"],
                },
            ],
        }
    )
    monkeypatch.setattr(service, "_call_vllm_message", recorder)

    result = await service.chat_with_rubric(
        [
            TeacherJudgeRubricChatMessage(
                role="user", content="檢查 Python 版本；檢查 Web 服務"
            )
        ],
        json.dumps({"items": []}, ensure_ascii=False),
        template_commands=[_general_command()],
    )

    assert "逐項分析" in result.reply
    assert "檢查 Python 版本" in result.reply
    assert "Web 服務回傳 200" in result.reply
    assert "服務 Port" in result.reply
    assert "check_steps" not in result.reply


@pytest.mark.asyncio
async def test_mixed_focus_gap_is_kept_when_model_omits_partial_candidate(
    monkeypatch: pytest.MonkeyPatch,
):
    """Recover a mixed-turn gap from conversation_focus, not only updated_items."""
    monkeypatch.setattr(system_ai_env, "vllm_model_name", "test-model")
    recorder = _CallRecorder()
    recorder.queue(
        {
            "reply": "Python 已整理成提案。",
            "proposal_status": "ready",
            "updated_items": [
                _ready_item("item-ready", "檢查 Python 版本", ["python3", "--version"])
            ],
            "conversation_focus": {
                "turn_kind": "requirement",
                "requirements": [
                    {
                        "focus_key": "Web 服務回傳 200",
                        "status": "needs_information",
                        "known_information": ["檢查 Web 服務"],
                        "missing_information": ["服務 Port"],
                    }
                ],
            },
        }
    )
    monkeypatch.setattr(service, "_call_vllm_message", recorder)

    result = await service.chat_with_rubric(
        [
            TeacherJudgeRubricChatMessage(
                role="user", content="檢查 Python 版本；檢查 Web 服務"
            )
        ],
        json.dumps({"items": []}, ensure_ascii=False),
        template_commands=[_general_command()],
    )

    assert result.proposal is not None
    assert [row["status"] for row in result.item_statuses] == [
        "ready",
        "needs_information",
    ]
    assert result.item_statuses[1]["missing_information"] == ["服務 Port"]
    assert "Web 服務回傳 200" in result.reply
    assert "服務 Port" in result.reply


@pytest.mark.asyncio
async def test_baseline_stateful_update_repair_injects_rubric_snapshot(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(system_ai_env, "vllm_model_name", "test-model")
    recorder = _CallRecorder()
    invalid_update = {
        **_ready_item("item-1", "檢查 Python 版本", ["python3", "--version"]),
        "operation": "update",
    }
    recorder.queue(
        {
            "reply": "已更新第 1 條。",
            "proposal_status": "ready",
            "updated_items": [invalid_update],
        }
    )
    recorder.queue(
        {
            "reply": "已更新第 1 條。",
            "proposal_status": "ready",
            "updated_items": [invalid_update],
        }
    )
    monkeypatch.setattr(service, "_call_vllm_message", recorder)

    reply, proposal, _ = await service.chat_with_rubric(
        [TeacherJudgeRubricChatMessage(role="user", content="把第 1 條改成 X")],
        json.dumps(
            {
                "items": [
                    {
                        "id": "item-1",
                        "title": "檢查 Python 版本",
                        "description": "原描述",
                        "detectable": "manual",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        rubric_available=True,
        template_commands=[_general_command()],
    )

    assert len(recorder.payloads) == 2
    repair_messages = recorder.payloads[1]["messages"]
    snapshot_messages = [
        message
        for message in repair_messages
        if "目前檢查表" in str(message.get("content") or "")
    ]
    assert snapshot_messages, "repair must inject the current rubric snapshot"
    assert proposal is not None


@pytest.mark.asyncio
async def test_baseline_false_ready_after_failed_repair_falls_back_to_gap_reply(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    monkeypatch.setattr(system_ai_env, "vllm_model_name", "test-model")
    ready_claim = {
        "reply": "已建立提案。",
        "proposal_status": "ready",
        "updated_items": [_port_gap_item()],
    }
    recorder = _CallRecorder()
    recorder.queue(ready_claim)
    recorder.queue(ready_claim)
    monkeypatch.setattr(service, "_call_vllm_message", recorder)

    with caplog.at_level("WARNING"):
        reply, proposal, _ = await service.chat_with_rubric(
            [TeacherJudgeRubricChatMessage(role="user", content="檢查 Web 服務")],
            json.dumps({"items": []}, ensure_ascii=False),
            template_commands=[_general_command()],
        )

    assert len(recorder.payloads) == 2
    assert proposal is None
    assert "Port" in reply or "缺少" in reply
    assert "ready_claim_without_valid_proposal" in caplog.text
