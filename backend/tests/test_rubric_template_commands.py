from __future__ import annotations

import json
import uuid
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from sqlmodel import Session, SQLModel, create_engine

from app.ai.teacher_judge import service as teacher_judge_service
from app.ai.teacher_judge.schemas import RubricItem
from app.ai.teacher_judge.template_command_service import (
    GENERAL_COMMAND,
    format_template_commands_for_prompt,
    get_enabled_template_commands,
    validate_check_steps,
)
from app.api.routes import rubric as rubric_route
from app.models.teacher_judge_template_command import TeacherJudgeTemplateCommand


def _patch_teacher_judge_vllm_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        teacher_judge_service,
        "settings",
        SimpleNamespace(
            VLLM_MODEL_NAME="test-model",
            VLLM_ENABLE_THINKING=False,
            VLLM_TIMEOUT=60,
            VLLM_MAX_TOKENS=4096,
            VLLM_CHAT_MAX_TOKENS=4096,
            VLLM_CHAT_TEMPERATURE=0.2,
            VLLM_TOP_P=1.0,
            VLLM_TOP_K=20,
            VLLM_REPETITION_PENALTY=1.0,
        ),
    )


def _session_with_commands() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(
        TeacherJudgeTemplateCommand(
            template_key="n8n",
            command_key="n8n.port_check",
            command_label="n8n 連接埠檢查",
            category="port",
            command_template="ss -lntp | grep ':5678'",
            description="檢查 n8n 預設 5678 連接埠是否正在監聽。",
        )
    )
    session.add(
        TeacherJudgeTemplateCommand(
            template_key="python",
            command_key="python.version",
            command_label="Python 版本",
            category="runtime",
            command_template="python3 --version",
            description="查看 Python 直譯器版本。",
            enabled=False,
        )
    )
    session.commit()
    return session


def _python_entrypoint_command() -> TeacherJudgeTemplateCommand:
    return TeacherJudgeTemplateCommand(
        template_key="python",
        command_key="python.run_entrypoint",
        command_label="執行 Python 程式入口",
        category="execution",
        command_template="python3 main.py",
        description="受控執行 Python 程式並收集結果。",
        risk_level="executes_code",
        requires_confirmation=True,
    )


def test_get_enabled_template_commands_filters_template_and_enabled() -> None:
    session = _session_with_commands()

    commands = get_enabled_template_commands(session, "n8n")

    assert [command.command_key for command in commands] == ["n8n.port_check"]


def test_get_enabled_template_commands_can_include_cross_template_catalog() -> None:
    session = _session_with_commands()
    session.add(
        TeacherJudgeTemplateCommand(
            template_key="python",
            command_key="python.run_entrypoint",
            command_label="執行 Python 程式入口",
            category="execution",
            command_template="python3 main.py",
            description="受控執行 Python 程式入口。",
        )
    )
    session.commit()

    commands = get_enabled_template_commands(
        session, "n8n", include_cross_template=True
    )

    assert [(command.template_key, command.command_key) for command in commands] == [
        ("n8n", "n8n.port_check"),
        ("linux", "system.run_command"),
        ("python", "python.run_entrypoint"),
    ]


def test_cross_template_catalog_includes_generic_controlled_command() -> None:
    session = _session_with_commands()

    commands = get_enabled_template_commands(
        session, "python", include_cross_template=True
    )
    general = next(
        command for command in commands if command.command_key == "system.run_command"
    )

    assert general.template_key == "linux"
    assert general.requires_confirmation is True
    assert "平台已登錄的通用能力" in general.description
    assert "適用所有通過平台政策的唯讀／診斷系統指令" in general.description
    assert "只是一部分範例" in general.description
    assert "cat" in general.description
    assert "cwd" in general.description
    assert "stdout" in general.description
    assert "stderr" in general.description
    assert "平台自動套用安全逾時上限" in general.description
    assert "不是要求老師新增權限" in general.description


def test_validate_check_steps_allows_catalog_backed_cross_template_step() -> None:
    python_command = _python_entrypoint_command()

    items = validate_check_steps(
        "n8n",
        [
            {
                "check_steps": [
                    {
                        "template_key": "python",
                        "command_key": "python.run_entrypoint",
                    },
                    {
                        "template_key": "postgresql",
                        "command_key": "python.run_entrypoint",
                    },
                ]
            }
        ],
        [python_command],
    )

    assert items[0]["check_steps"] == [
        {
            "template_key": "python",
            "command_key": "python.run_entrypoint",
            "command_label": "執行 Python 程式入口",
        }
    ]


def test_validate_generic_command_applies_platform_timeout_default() -> None:
    items = validate_check_steps(
        "linux",
        [
            {
                "check_steps": [
                    {
                        "template_key": "linux",
                        "command_key": "system.run_command",
                        "parameters": {
                            "cwd": r"C:\Users\陳洋\Desktop\Campus-Cloud",
                            "argv": ["cat", ".env"],
                            "success_criteria": "exit code 為 0",
                        },
                    }
                ]
            }
        ],
        [GENERAL_COMMAND],
    )

    parameters = items[0]["check_steps"][0]["parameters"]
    assert parameters == {
        "cwd": r"C:\Users\陳洋\Desktop\Campus-Cloud",
        "argv": ["cat", ".env"],
        "success_criteria": "exit code 為 0",
        "timeout_seconds": 30,
    }


def test_generic_command_internal_fields_are_not_teacher_missing_information() -> None:
    normalized = teacher_judge_service._normalize_rubric_items(
        [
            {
                "id": "item-1",
                "title": "讀取環境設定",
                "description": "在目前目錄讀取 .env。",
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
                            "cwd": r"C:\Users\陳洋\Desktop\Campus-Cloud",
                            "argv": ["cat", ".env"],
                            "success_criteria": "exit code 為 0",
                        },
                    }
                ],
            }
        ],
        template_key="linux",
        template_commands=[GENERAL_COMMAND],
    )

    assert normalized[0].detectable == "auto"
    assert normalized[0].missing_information == []
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
        "要檢查的檔案、服務或記錄範圍"
    ]


def test_cat_config_assignment_resolves_redundant_success_condition_gap() -> None:
    normalized = teacher_judge_service._normalize_rubric_items(
        [
            {
                "id": "item-1",
                "title": "確認 Web URL 設定",
                "description": "讀取 .env，確認有 web_URL=True 這條設定。",
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
                            "cwd": r"C:\Users\陳洋\Desktop\Campus-Cloud",
                            "argv": ["cat", ".env"],
                        },
                    }
                ],
            }
        ],
        template_key="linux",
        template_commands=[GENERAL_COMMAND],
    )

    item = normalized[0]
    assert item.detectable == "auto"
    assert item.missing_information == []
    assert item.check_steps[0].parameters["success_criteria"] == (
        "exit code 為 0，且輸出中存在設定行 `web_URL=True`"
        "（允許行首尾及等號周圍空白）"
    )
    assert item.check_steps[0].parameters["timeout_seconds"] == 30


@pytest.mark.asyncio
async def test_analyze_rubric_injects_catalog_and_normalizes_check_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = TeacherJudgeTemplateCommand(
        template_key="n8n",
        command_key="n8n.port_check",
        command_label="n8n 連接埠檢查",
        category="port",
        command_template="ss -lntp | grep ':5678'",
        description="檢查 n8n 預設 5678 連接埠是否正在監聽。",
    )
    captured_payload = {}

    async def fake_call_vllm(payload, timeout=60.0):
        captured_payload.update(payload)
        return (
            json.dumps(
                {
                    "items": [
                        {
                            "id": "item-1",
                            "title": "n8n 服務可啟動",
                            "checked": True,
                            "detectable": "auto",
                            "detection_method": "檢查 n8n port",
                            "check_steps": [
                                {
                                    "template_key": "n8n",
                                    "command_key": "n8n.port_check",
                                },
                                {
                                    "template_key": "n8n",
                                    "command_key": "n8n.missing",
                                },
                            ],
                        }
                    ],
                    "summary": "ok",
                }
            ),
            {"total_tokens": 1},
        )

    monkeypatch.setattr(teacher_judge_service, "_call_vllm", fake_call_vllm)
    _patch_teacher_judge_vllm_settings(monkeypatch)

    analysis, _metrics = await teacher_judge_service.analyze_rubric(
        "rubric text",
        template_key="n8n",
        template_commands=[command],
        environment_keys=["n8n", "python"],
    )

    system_prompt = captured_payload["messages"][0]["content"]
    assert "目前主要 template：n8n" in system_prompt
    assert "老師選定的評分環境：n8n, python" in system_prompt
    assert "n8n.port_check" in system_prompt
    assert "ss -lntp" not in system_prompt
    assert "不得自行發明" in system_prompt
    assert analysis.items[0].check_steps[0].command_key == "n8n.port_check"
    assert analysis.items[0].check_steps[0].command_label == "n8n 連接埠檢查"
    assert len(analysis.items[0].check_steps) == 1
    assert analysis.items[0].checked is False


@pytest.mark.asyncio
async def test_chat_with_rubric_validates_returned_check_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = TeacherJudgeTemplateCommand(
        template_key="n8n",
        command_key="n8n.http_check",
        command_label="n8n HTTP 檢查",
        category="service",
        command_template="curl -I --max-time 5 http://127.0.0.1:5678",
        description="檢查本機 n8n Web 服務是否有 HTTP 回應。",
    )
    captured_payload = {}

    async def fake_call_vllm(payload, timeout=60.0):
        captured_payload.update(payload)
        return (
            json.dumps(
                {
                    "reply": "已更新",
                    "updated_items": [
                        {
                            "id": "item-1",
                            "title": "n8n Web UI",
                            "detectable": "auto",
                            "check_steps": [
                                {
                                    "template_key": "n8n",
                                    "command_key": "n8n.http_check",
                                },
                                {
                                    "template_key": "n8n",
                                    "command_key": "n8n.missing",
                                },
                            ],
                        }
                    ],
                }
            ),
            {"total_tokens": 1},
        )

    monkeypatch.setattr(teacher_judge_service, "_call_vllm", fake_call_vllm)
    _patch_teacher_judge_vllm_settings(monkeypatch)

    _reply, updated_items, _metrics = await teacher_judge_service.chat_with_rubric(
        messages=[SimpleNamespace(role="user", content="照這樣改")],
        rubric_context=json.dumps({"items": [{"id": "item-1"}]}),
        template_key="n8n",
        template_commands=[command],
    )

    assert updated_items is not None
    system_prompt = captured_payload["messages"][0]["content"]
    assert "目前主要 template：n8n" in system_prompt
    assert "n8n.http_check" in system_prompt
    assert "curl -I" not in system_prompt
    assert updated_items[0]["check_steps"] == [
            {
                "template_key": "n8n",
                "command_key": "n8n.http_check",
                "command_label": "n8n HTTP 檢查",
                "parameters": {},
            }
    ]


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

    async def fake_call_vllm(payload, timeout=60.0):
        captured_payload.update(payload)
        return (
            json.dumps(
                {
                    "reply": "已新增可自動檢查的項目。",
                    "updated_items": [
                        {
                            "id": "item-1",
                            "title": "main.py 執行結果",
                            "description": "執行 main.py，確認無錯誤並輸出整數 20。",
                            "detectable": "auto",
                            "detection_method": (
                                "執行 main.py，依 exit code 與 stderr 判斷錯誤，"
                                "並精確比對 stdout 是否為整數 20。"
                            ),
                            "fallback": None,
                            "check_steps": [
                                {
                                    "template_key": "python",
                                    "command_key": "python.run_entrypoint",
                                    "parameters": {
                                        "cwd": "/home/student/project",
                                        "argv": ["python3", "main.py"],
                                        "timeout_seconds": 30,
                                        "success_criteria": "exit code 為 0 且 stdout 等於 20",
                                    },
                                }
                            ],
                        }
                    ],
                }
            ),
            {"total_tokens": 1},
        )

    monkeypatch.setattr(teacher_judge_service, "_call_vllm", fake_call_vllm)
    _patch_teacher_judge_vllm_settings(monkeypatch)

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
    assert "`auto` 表示「自動檢測支援完整」" in system_prompt
    assert "執行 main.py，確認無錯誤並輸出整數 20" in system_prompt
    assert (
        "缺少無法由上下文得知的工作目錄、檔案、服務名稱、Port、記錄範圍或成功條件"
        in system_prompt
    )
    assert "主觀條件或平台沒有安全取證能力" in system_prompt
    assert "`auto` 項目的 `check_steps` 必須引用該 `command_key`" in system_prompt
    assert "`checked` 表示是否已達成" in system_prompt
    assert "`auto` 項目的 `missing_information` 必須是空陣列" in system_prompt
    assert "python.run_entrypoint" in system_prompt
    assert updated_items is not None
    assert updated_items[-1]["detectable"] == "auto"
    assert updated_items[-1]["check_steps"][0]["command_key"] == (
        "python.run_entrypoint"
    )


@pytest.mark.asyncio
async def test_chat_prompt_accepts_generic_cat_env_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_payload = {}

    async def fake_call_vllm(payload, timeout=60.0):
        captured_payload.update(payload)
        return (
            json.dumps(
                {
                    "reply": "已新增可自動檢查的項目。",
                    "updated_items": [
                        {
                            "id": "item-1",
                            "title": "讀取環境設定",
                            "description": "在專案目錄執行 cat .env 並回傳內容。",
                            "detectable": "auto",
                            "detection_method": (
                                "以 argv ['cat', '.env']、指定 cwd 與 timeout 執行，"
                                "並原樣取得 exit code、stdout、stderr。"
                            ),
                            "fallback": None,
                            "check_steps": [
                                {
                                    "template_key": "linux",
                                    "command_key": "system.run_command",
                                    "parameters": {
                                        "cwd": "/home/student/project",
                                        "argv": ["cat", ".env"],
                                        "timeout_seconds": 10,
                                        "success_criteria": "exit code 為 0",
                                    },
                                }
                            ],
                        }
                    ],
                }
            ),
            {"total_tokens": 1},
        )

    monkeypatch.setattr(teacher_judge_service, "_call_vllm", fake_call_vllm)
    _patch_teacher_judge_vllm_settings(monkeypatch)

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
    assert "平台已登錄、可供後續檢查腳本使用" in system_prompt
    assert "本次 AI 對話只規劃評分項目與 check_steps" in system_prompt
    assert "不需要老師再新增指令或權限" in system_prompt
    assert "argv 與安全逾時由 AI／平台依 catalog 規劃" in system_prompt
    assert r"C:\Users\陳洋\Desktop\Campus-Cloud>" in system_prompt
    assert '["cat", ".env"]' in system_prompt
    assert "原樣收集 exit code、stdout、stderr" in system_prompt
    assert "cd 請以 cwd 表示" in system_prompt
    assert updated_items is not None
    assert updated_items[0]["detectable"] == "auto"
    assert updated_items[0]["check_steps"][0]["command_key"] == (
        "system.run_command"
    )


@pytest.mark.asyncio
async def test_chat_prompt_treats_attachment_as_concrete_rubric_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_payload = {}

    async def fake_call_vllm(payload, timeout=60.0):
        captured_payload.update(payload)
        return (
            json.dumps(
                {
                    "reply": "已依附件整理評分項目。",
                    "updated_items": [
                        {
                            "id": "item-1",
                            "title": "服務 Port",
                            "description": "確認預期服務 Port 正在監聽。",
                            "checked": False,
                            "detectable": "auto",
                            "detection_method": "檢查 listening ports。",
                            "fallback": None,
                        }
                    ],
                }
            ),
            {"total_tokens": 1},
        )

    monkeypatch.setattr(teacher_judge_service, "_call_vllm", fake_call_vllm)
    _patch_teacher_judge_vllm_settings(monkeypatch)

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
    assert "附件中的可讀文字就是老師提供的具體內容" in system_prompt
    assert "不要因目前項目數為 0 就回覆尚未提供內容" in system_prompt
    assert "附件表格的每一列可轉成一個評分項目" in system_prompt
    assert captured_payload["messages"][-1]["role"] == "user"
    assert "請直接逐條核查，不要求教師再使用「新增」句型" in (
        captured_payload["messages"][-1]["content"]
    )
    assert "附件中有 Ready 變更時請依提案輸出模式回傳 updated_items" in (
        captured_payload["messages"][-1]["content"]
    )
    assert updated_items is not None
    assert updated_items[0]["title"] == "服務 Port"


def test_normalize_marks_auto_without_valid_check_steps_as_unsupported() -> None:
    items = teacher_judge_service._normalize_rubric_items(
        [
            {
                "title": "未知檢查",
                "detectable": "auto",
                "check_steps": [{"template_key": "n8n", "command_key": "missing"}],
            }
        ],
        template_key="n8n",
        template_commands=[],
    )

    assert items == [
        RubricItem(
            id="item-1",
            title="未知檢查",
            description="",
            checked=False,
                detectable="manual",
                detection_method="目前沒有可引用的有效 command_key，缺少自動取得客觀證據的能力",
                fallback="目前平台不支援此項目的安全自動檢測。",
                check_steps=[],
        )
    ]


def test_normalize_preserves_objectively_verifiable_main_py_checkpoint() -> None:
    command = _python_entrypoint_command()
    items = teacher_judge_service._normalize_rubric_items(
        [
            {
                "title": "main.py 執行結果",
                "description": "執行 main.py，確認無錯誤並輸出整數 20。",
                "detectable": "auto",
                "detection_method": (
                    "以 exit code 與 stderr 判斷錯誤，並精確比對 stdout 是否為整數 20。"
                ),
                "fallback": "請人工執行。",
                "check_steps": [
                    {
                        "template_key": "python",
                        "command_key": "python.run_entrypoint",
                        "parameters": {
                            "cwd": "/home/student/project",
                            "argv": ["python3", "main.py"],
                            "timeout_seconds": 30,
                            "success_criteria": "exit code 為 0 且 stdout 等於 20",
                        },
                    }
                ],
            }
        ],
        template_key="python",
        template_commands=[command],
    )

    assert items[0].detectable == "auto"
    assert items[0].check_steps[0].command_key == "python.run_entrypoint"
    assert "stdout" in (items[0].detection_method or "")
    assert items[0].fallback is None


def test_normalize_marks_missing_python_parameters_as_missing_information() -> None:
    items = teacher_judge_service._normalize_rubric_items(
        [
            {
                "title": "main.py 執行結果",
                "detectable": "auto",
                "detection_method": "執行 main.py 並檢查 stdout",
                "check_steps": [
                    {
                        "template_key": "python",
                        "command_key": "python.run_entrypoint",
                        "parameters": {
                            "argv": ["python3", "main.py"],
                            "timeout_seconds": 30,
                            "success_criteria": "stdout 等於 20",
                        },
                    }
                ],
            }
        ],
        template_key="python",
        template_commands=[_python_entrypoint_command()],
    )

    assert items[0].detectable == "partial"
    assert items[0].missing_information == ["main.py 所在的工作目錄"]


def test_normalize_python_code_quality_stays_manual() -> None:
    items = teacher_judge_service._normalize_rubric_items(
        [{"title": "評估 main.py 的架構品質", "detectable": "manual"}],
        template_key="python",
        template_commands=[_python_entrypoint_command()],
    )

    assert items[0].detectable == "manual"
    assert items[0].check_steps == []


@pytest.mark.asyncio
async def test_upload_rubric_defaults_linux_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session_with_commands()

    async def fake_analyze_rubric(raw_text, template_key, template_commands):
        assert raw_text == "parsed text"
        assert template_key == "linux"
        assert [command.command_key for command in template_commands] == [
            "system.run_command",
            "n8n.port_check"
        ]
        return (
            SimpleNamespace(model_dump=lambda: {"items": []}),
            {"total_tokens": 0},
        )

    monkeypatch.setattr(rubric_route, "parse_document", lambda *_args: "parsed text")
    monkeypatch.setattr(rubric_route, "analyze_rubric", fake_analyze_rubric)

    response = await rubric_route.upload_rubric(
        current_user=SimpleNamespace(id=uuid.uuid4(), email="teacher@example.com"),
        session=session,
        file=UploadFile(filename="rubric.pdf", file=BytesIO(b"pdf")),
        template_key="linux",
    )

    assert response["template_key"] == "linux"


@pytest.mark.asyncio
async def test_upload_rubric_rejects_unknown_template() -> None:
    session = _session_with_commands()

    with pytest.raises(HTTPException) as exc_info:
        await rubric_route.upload_rubric(
            current_user=SimpleNamespace(email="teacher@example.com"),
            session=session,
            file=UploadFile(filename="rubric.pdf", file=BytesIO(b"pdf")),
            template_key="unknown",
        )

    assert exc_info.value.status_code == 400


def test_prompt_formatter_handles_empty_catalog() -> None:
    assert "沒有 template command catalog" in format_template_commands_for_prompt([])


def test_prompt_formatter_does_not_expose_raw_shell_command() -> None:
    formatted = format_template_commands_for_prompt(
        [
            TeacherJudgeTemplateCommand(
                template_key="n8n",
                command_key="n8n.http_check",
                command_label="n8n HTTP 檢查",
                category="service",
                command_template="curl -I --max-time 5 http://127.0.0.1:5678",
                description="檢查本機 n8n Web 服務是否有 HTTP 回應。",
            )
        ]
    )

    assert "n8n.http_check" in formatted
    assert "template_key: n8n" in formatted
    assert "curl -I" not in formatted
