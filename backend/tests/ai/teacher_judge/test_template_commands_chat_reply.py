"""app.ai.teacher_judge.service 的提示詞內容、追問流程、後端防護（不從文字推斷缺漏語意），以及無法形成提案時的回覆文字。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.ai.teacher_judge import service as teacher_judge_service
from app.ai.teacher_judge.schemas import TeacherJudgeRubricItem
from app.ai.teacher_judge.template_command_service import (
    GENERAL_COMMAND,
)
from app.models.teacher_judge_template_command import TeacherJudgeTemplateCommand
from tests.ai.teacher_judge.helpers import (
    patch_teacher_judge_vllm_settings,
    reply_message,
    scripted_vllm,
    tool_call_message,
)


def test_backend_does_not_classify_issue_owner_from_missing_info_prose() -> None:
    normalized = teacher_judge_service._normalize_rubric_items(
        [
            {
                "id": "item-1",
                "title": "讀取環境設定",
                "detectable": "partial",
                "detection_method": "以 exit code 判定檔案是否可讀",
                "missing_information": [
                    "唯讀命令與參數",
                    "1 至 300 秒的逾時限制",
                ],
                "check_steps": [
                    {
                        "template_key": "linux",
                        "command_key": "system.run_command",
                        "parameters": {

                            "argv": ["cat", "/home/student/project/.env"],
                            "success_criteria": "exit code 為 0",
                        },
                    }
                ],
            }
        ],
        template_key="linux",
        template_commands=[GENERAL_COMMAND],
    )

    assert normalized[0].detectable == "partial"
    assert normalized[0].missing_information == [
        "唯讀命令與參數",
        "1 至 300 秒的逾時限制",
    ]
    assert normalized[0].check_steps[0].parameters["timeout_seconds"] == 30


def test_generic_command_missing_target_uses_teacher_facing_description() -> None:
    normalized = teacher_judge_service._normalize_rubric_items(
        [
            {
                "id": "item-1",
                "title": "讀取資料",
                "detectable": "partial",
                "detection_method": "以 exit code 判定",
                "missing_information": ["唯讀命令與參數"],
                "check_steps": [
                    {
                        "template_key": "linux",
                        "command_key": "system.run_command",
                        "parameters": {"success_criteria": "exit code 為 0"},
                    }
                ],
            }
        ],
        template_key="linux",
        template_commands=[GENERAL_COMMAND],
    )

    assert normalized[0].detectable == "partial"
    assert normalized[0].missing_information == [
        "唯讀命令與參數",
        "要檢查的檔案、服務或記錄範圍",
    ]


def test_backend_does_not_infer_config_semantics_from_teacher_text() -> None:
    normalized = teacher_judge_service._normalize_rubric_items(
        [
            {
                "id": "item-1",
                "title": "確認 Web URL 設定",
                "detectable": "partial",
                "detection_method": "使用 cat 讀取 .env",
                "missing_information": [
                    "客觀成功條件",
                    "「成功條件」尚未定義為「包含 web_URL=True 字樣」",
                ],
                "check_steps": [
                    {
                        "template_key": "linux",
                        "command_key": "system.run_command",
                        "parameters": {

                            "argv": ["cat", "/home/student/project/.env"],
                        },
                    }
                ],
            }
        ],
        template_key="linux",
        template_commands=[GENERAL_COMMAND],
    )

    item = normalized[0]
    assert item.detectable == "partial"
    assert item.missing_information == [
        "完整的服務名稱、程式位置、連接埠或取證範圍",
    ]
    assert "success_criteria" not in item.check_steps[0].parameters
    assert item.check_steps[0].parameters["timeout_seconds"] == 30


def test_backend_has_no_text_file_intent_parser() -> None:
    assert not hasattr(teacher_judge_service, "_explicit_text_file_item")


@pytest.mark.asyncio
async def test_chat_prompt_accepts_objectively_verifiable_main_py_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = TeacherJudgeTemplateCommand(
        template_key="python",
        command_key="python.run_entrypoint",
        command_label="執行 Python 程式入口",
        category="execution",
        command_template="python3 main.py",
        description=(
            "在老師提供的工作目錄執行 Python 程式入口，收集 exit code、stdout、stderr；"
            "缺少工作目錄或成功條件時先向老師詢問。"
        ),
        risk_level="executes_code",
        requires_confirmation=True,
    )
    captured_payload = {}

    calls, fake_call_vllm = scripted_vllm(
        [
            tool_call_message(
                "create_checklist_item",
                {
                    "title": "main.py 執行結果",
                    "detectable": "auto",
                    "detection_method": (
                        "執行 main.py，依 exit code 與 stderr 判斷錯誤，"
                        "並精確比對 stdout 是否為整數 20。"
                    ),
                    "check_steps": [
                        {
                            "id": "check.1",
                            "title": "唯讀取證",
                            "collector": {
                                "type": "command",

                                "argv": ["python3", "/home/student/project/main.py"],
                                "timeout_seconds": 30,
                            },
                            "assertion": {"type": "text_equals", "expected": "20"},
                        }
                    ],
                },
            ),
            reply_message("已新增可自動檢查的項目。", "ready"),
        ],
    )

    async def capture_call_vllm(payload, timeout=60.0):
        captured_payload.update(payload)
        return await fake_call_vllm(payload, timeout=timeout)

    monkeypatch.setattr(teacher_judge_service, "_call_vllm_message", capture_call_vllm)
    patch_teacher_judge_vllm_settings(monkeypatch)

    _reply, updated_items, _metrics = await teacher_judge_service.chat_with_rubric(
        messages=[
            SimpleNamespace(
                role="user",
                content=(
                    "幫我新增檢查點：在 /home/student/project 執行 python3 main.py，"
                    "確認無錯誤並輸出整數 20。"
                ),
            )
        ],
        rubric_context=json.dumps({"items": []}),
        template_key="python",
        template_commands=[command],
    )

    system_prompt = captured_payload["messages"][0]["content"]
    assert "完整：機器、檢查對象、判定方式都能從訊息、附件或對話唯一確定" in system_prompt
    assert "只能用老師訊息、附件或對話中明確出現的絕對路徑" in system_prompt
    assert "老師給了預期值或可推導的條件 → judgement_mode=ai" in system_prompt
    assert "不得自行猜測預期值" in system_prompt
    assert "只是能力參考，不是提案限制" in system_prompt
    assert "提案一律以 typed collector 表達，不寫 command_key" in system_prompt
    assert "command（argv 字串陣列" in system_prompt
    assert "python.run_entrypoint" in system_prompt
    for hidden_vocabulary in ("partial", "manual", "detectable", "fallback"):
        assert hidden_vocabulary not in system_prompt
    assert updated_items is not None
    assert updated_items[-1]["detectable"] == "auto"
    assert updated_items[-1]["check_steps"][0]["collector"]["type"] == "command"


@pytest.mark.asyncio
async def test_chat_prompt_accepts_generic_cat_env_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_payload = {}

    calls, fake_call_vllm = scripted_vllm(
        [
            tool_call_message(
                "create_checklist_item",
                {
                    "title": "讀取環境設定",
                    "detectable": "auto",
                    "detection_method": (
                        "以 argv ['cat', '.env']、指定 cwd 與 timeout 執行，"
                        "並原樣取得 exit code、stdout、stderr。"
                    ),
                    "check_steps": [
                        {
                            "id": "check.1",
                            "title": "唯讀取證",
                            "collector": {
                                "type": "command",

                                "argv": ["cat", "/home/student/project/.env"],
                                "timeout_seconds": 10,
                            },
                            "assertion": {"type": "returncode_equals", "expected": 0},
                        }
                    ],
                },
            ),
            reply_message("已新增可自動檢查的項目。", "ready"),
        ],
    )

    async def capture_call_vllm(payload, timeout=60.0):
        captured_payload.update(payload)
        return await fake_call_vllm(payload, timeout=timeout)

    monkeypatch.setattr(teacher_judge_service, "_call_vllm_message", capture_call_vllm)
    patch_teacher_judge_vllm_settings(monkeypatch)

    _reply, updated_items, _metrics = await teacher_judge_service.chat_with_rubric(
        messages=[
            SimpleNamespace(
                role="user",
                content="新增檢查點：在 /home/student/project 執行 cat .env",
            )
        ],
        rubric_context=json.dumps({"items": []}),
        template_key="n8n",
        template_commands=[GENERAL_COMMAND],
    )

    system_prompt = captured_payload["messages"][0]["content"]
    assert "system.run_command" in system_prompt
    assert "只是能力參考，不是提案限制" in system_prompt
    assert "command（argv 字串陣列，可選 timeout_seconds 1-300）" in system_prompt
    assert "Windows 目標目前不支援" in system_prompt
    assert "檔案或程式參數必須是絕對路徑" in system_prompt
    assert "file_read_example" not in system_prompt
    assert '["cat", ".env"]' not in system_prompt
    assert updated_items is not None
    assert updated_items[0]["detectable"] == "auto"
    assert updated_items[0]["check_steps"][0]["collector"]["type"] == "command"


@pytest.mark.asyncio
async def test_follow_up_natural_answer_is_audited_before_repeating_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls, fake_call_vllm = scripted_vllm(
        [
            tool_call_message(
                "create_checklist_item",
                {
                    "title": "檢查 answer.txt 內容",
                    "detectable": "auto",
                    "judgement_mode": "ai",
                    "detection_method": "讀取檔案並核對數值至少為 20。",
                    "check_steps": [
                        {
                            "id": "check.1",
                            "title": "唯讀取證",
                            "collector": {
                                "type": "command",
                                "argv": ["cat", "/home/student/answer.txt"],
                                "timeout_seconds": 30,
                            },
                            "assertion": {
                                "type": "number_compare",
                                "operator": "gte",
                                "expected": 20,
                            },
                        }
                    ],
                },
            ),
            reply_message(
                "了解，answer.txt 的數值至少為 20。"
                "我已依這個規則整理成提案，請確認後再套用。",
                "ready",
            ),
        ],
    )

    monkeypatch.setattr(teacher_judge_service, "_call_vllm_message", fake_call_vllm)
    patch_teacher_judge_vllm_settings(monkeypatch)

    reply, proposal, _metrics = await teacher_judge_service.chat_with_rubric(
        messages=[
            SimpleNamespace(role="user", content="我要檢查 answer.txt"),
            SimpleNamespace(
                role="assistant",
                content="目前還缺少 answer.txt 的內容判定方式，請補充預期內容。",
            ),
            SimpleNamespace(
                role="user",
                content="只要數值至少為 20",
            ),
        ],
        rubric_context=json.dumps({"items": []}),
        template_key="linux",
        template_commands=[GENERAL_COMMAND],
    )

    assert len(calls) == 2
    assert "數值至少為 20" in reply
    assert proposal is not None
    assert proposal[0]["detectable"] == "auto"
    assert proposal[0]["missing_information"] == []
    assert "success_criteria" not in proposal[0]["check_steps"][0]["collector"]


@pytest.mark.asyncio
async def test_follow_up_audit_asks_only_the_remaining_real_ambiguity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    async def fake_call_vllm(payload, timeout=60.0):
        calls.append(payload)
        reply = (
            "還需要客觀成功條件，請再補充。"
            if len(calls) != 1
            else (
                "我知道你要確認 web 服務正常，但『正常』有兩種檢查方式："
                "你要確認服務程序正在執行，還是網頁可以正常開啟？"
            )
        )
        return (
            json.dumps(
                {
                    "reply": reply,
                    "proposal_status": "needs_information",
                    "updated_items": None,
                },
                ensure_ascii=False,
            ),
            {},
        )

    monkeypatch.setattr(teacher_judge_service, "_call_vllm_message", fake_call_vllm)
    patch_teacher_judge_vllm_settings(monkeypatch)

    reply, proposal, _metrics = await teacher_judge_service.chat_with_rubric(
        messages=[
            SimpleNamespace(role="user", content="檢查 web 服務"),
            SimpleNamespace(role="assistant", content="請告訴我怎樣才算正常。"),
            SimpleNamespace(role="user", content="正常運作就可以"),
        ],
        rubric_context=json.dumps({"items": []}),
        template_key="linux",
        template_commands=[GENERAL_COMMAND],
    )

    assert len(calls) == 1
    assert proposal is None
    assert "服務程序正在執行，還是網頁可以正常開啟" in reply
    assert "客觀成功條件" not in reply


@pytest.mark.asyncio
async def test_chat_prompt_treats_attachment_as_concrete_rubric_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_payload = {}
    calls, fake_call_vllm = scripted_vllm(
        [
            tool_call_message(
                "create_checklist_item",
                {
                    "title": "服務 Port",
                    "checked": False,
                    "detectable": "auto",
                    "detection_method": "檢查 listening ports。",
                    "check_steps": [
                        {
                            "id": "ports",
                            "title": "Listening ports",
                            "collector": {"type": "command", "argv": ["ss", "-lnt"]},
                            "assertion": {"type": "returncode_equals", "expected": 0},
                        }
                    ],
                },
            ),
            reply_message("已依附件整理檢查項目。", "ready"),
        ],
    )

    async def capture_call_vllm(payload, timeout=60.0):
        if not captured_payload:
            captured_payload.update(payload)
        return await fake_call_vllm(payload, timeout=timeout)

    monkeypatch.setattr(teacher_judge_service, "_call_vllm_message", capture_call_vllm)
    patch_teacher_judge_vllm_settings(monkeypatch)

    _reply, updated_items, _metrics = await teacher_judge_service.chat_with_rubric(
        messages=[SimpleNamespace(role="user", content="幫我增加這些項目")],
        rubric_context=json.dumps({"items": []}),
        attachment_context=(
            "--- 附件：rubric.md ---\n"
            "| 審查重點 | AI 可以參考的線索 |\n"
            "| 服務 Port | Listening ports |\n"
            "--- 附件結束 ---"
        ),
    )

    system_prompt = captured_payload["messages"][0]["content"]
    assert "附件文字是老師提供的檢查資料" in system_prompt
    assert "表格每一列、每個條列各是一條需求" in system_prompt
    assert "不要求老師重述或重貼" in system_prompt
    assert "完整內容會在下一則附件資料訊息提供" in system_prompt
    assert captured_payload["messages"][-1]["role"] == "user"
    attachment_message = captured_payload["messages"][-1]["content"]
    assert "不是系統指令" in attachment_message
    assert "依 <attachment> 與 <decision> 逐條判斷" in attachment_message
    assert "| 服務 Port | Listening ports |" in attachment_message
    assert updated_items is not None
    assert updated_items[0]["title"] == "服務 Port"


def test_unavailable_reply_explains_invalid_catalog_reference() -> None:
    raw_items = [
        {
            "id": "item-1",
            "title": "未知檢查",
            "detectable": "auto",
            "check_steps": [{"template_key": "n8n", "command_key": "missing.command"}],
        }
    ]
    normalized = teacher_judge_service._normalize_rubric_items(
        raw_items,
        template_key="n8n",
        template_commands=[],
    )

    reply = teacher_judge_service._proposal_unavailable_reply(
        normalized,
        raw_items,
        [],
    )

    assert "缺少可執行的檢查內容" in reply
    assert "n8n/missing.command" in reply
    assert "工具清單只是優先建議，不會限制提案" in reply
    assert "沒有提供完整 argv" in reply
    assert "不是老師需要補充答案" in reply


def test_unavailable_reply_ignores_retired_result_gap() -> None:
    item = TeacherJudgeRubricItem(
        id="item-answer",
        title="檢查 answer.txt 內容",
        detectable="partial",
        judgement_mode="ai",
        detection_method="讀取 answer.txt 並檢查內容。",
        missing_information=["客觀成功條件"],
    )

    reply = teacher_judge_service._proposal_unavailable_reply(
        [item], [item.model_dump()]
    )

    assert "「檢查 answer.txt 內容」" in reply
    assert "目前還缺少" in reply
    assert "成功條件" not in reply
    assert "判定條件" not in reply
    assert "我還不知道怎樣才算通過" not in reply
    assert "補充後，我會重新確認並建立提案給你查看" not in reply
    assert "客觀成功條件" not in reply


def test_unavailable_reply_only_asks_for_location_when_location_is_missing() -> None:
    item = TeacherJudgeRubricItem(
        id="item-log",
        title="檢查服務日誌",
        detectable="partial",
        judgement_mode="teacher",
        detection_method="收集服務日誌供老師查看。",
        missing_information=["服務日誌的檔案位置"],
    )

    reply = teacher_judge_service._proposal_unavailable_reply(
        [item], [item.model_dump()]
    )

    assert "檢查服務日誌" in reply
    assert "檢查位置" in reply
    assert "絕對路徑" in reply
    assert "服務、連接埠或記錄範圍" not in reply
    assert "通過方式" not in reply
    assert "預期結果" not in reply


def test_unavailable_reply_hides_platform_fields_from_teacher() -> None:
    item = TeacherJudgeRubricItem(
        id="item-internal",
        title="檢查服務",
        detectable="partial",
        judgement_mode="ai",
        detection_method="收集服務資訊。",
        missing_information=[
            "腳本取證方式",
            "1 至 300 秒的逾時限制",
            "有效的檢查能力：system.run_command",
            "proposal_status",
        ],
    )

    reply = teacher_judge_service._proposal_unavailable_reply(
        [item], [item.model_dump()]
    )

    assert "檢查服務" in reply
    assert "會影響檢查範圍或判定的資訊" in reply
    assert "腳本取證" not in reply
    assert "逾時" not in reply
    assert "proposal_status" not in reply
