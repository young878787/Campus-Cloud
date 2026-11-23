"""app/ai/teacher_judge/prompt.py 的對話 system prompt 文字契約：範圍限制、缺資訊追問、診斷指令原則與結構化 payload 長度上限。"""

from __future__ import annotations

from app.ai.teacher_judge.prompt import CHAT_SYSTEM_TEMPLATE, SITUATION_NORMAL


def test_teacher_judge_chat_prompt_is_scoped_and_clarifies_missing_information():
    assert "使用者問 A，只回答 A" in CHAT_SYSTEM_TEMPLATE
    assert "只詢問最少且具體的問題" in CHAT_SYSTEM_TEMPLATE
    assert "不得猜測後繼續" in CHAT_SYSTEM_TEMPLATE
    assert "不要補充未詢問的" in CHAT_SYSTEM_TEMPLATE
    assert "只協助老師規劃、新增或調整檢查項目" in CHAT_SYSTEM_TEMPLATE
    assert "不會當場連線學生環境、讀取檔案或執行指令" in CHAT_SYSTEM_TEMPLATE
    assert "不是提案白名單" in CHAT_SYSTEM_TEMPLATE
    assert "不得只因沒有專用 `command_key` 就拒絕提案" in CHAT_SYSTEM_TEMPLATE
    assert "要求老師新增權限" in CHAT_SYSTEM_TEMPLATE
    assert "不要求老師先說「新增」" in CHAT_SYSTEM_TEMPLATE
    assert "一則訊息包含多條需求時逐條拆解" in CHAT_SYSTEM_TEMPLATE
    assert "不得因其中一條不完整而忽略其他 Ready 需求" in CHAT_SYSTEM_TEMPLATE
    assert "不得因缺少客觀答案而攔截提案" in CHAT_SYSTEM_TEMPLATE
    assert "只有老師明確要求「重新核查整張檢查表」" in CHAT_SYSTEM_TEMPLATE
    assert "不得只說「資訊不足」" in CHAT_SYSTEM_TEMPLATE
    assert "像助教當面說明的日常繁體中文" in CHAT_SYSTEM_TEMPLATE
    assert "先說已經知道什麼，再說還缺什麼" in CHAT_SYSTEM_TEMPLATE
    assert "完整路徑" in CHAT_SYSTEM_TEMPLATE
    assert "工作目錄與相對路徑" in CHAT_SYSTEM_TEMPLATE
    assert "預期文字、數字、行數、欄位、版本、Port 或狀態" in (
        CHAT_SYSTEM_TEMPLATE
    )
    assert "老師明確表示想自己檢查時，才說明會先收集結果再由老師查看" in (
        CHAT_SYSTEM_TEMPLATE
    )
    assert "不得自行改用 `teacher`" in CHAT_SYSTEM_TEMPLATE
    assert "應使用 `auto + teacher`" not in CHAT_SYSTEM_TEMPLATE
    assert "一般回覆不要使用「腳本取證」" in CHAT_SYSTEM_TEMPLATE
    assert "依項目的檢查對象與缺口自然組句" in CHAT_SYSTEM_TEMPLATE
    assert "不要固定套用任何預設開頭、結尾或完整範本" in (
        CHAT_SYSTEM_TEMPLATE
    )
    assert "不要照抄範例、硬塞檔名或重複固定收尾" in CHAT_SYSTEM_TEMPLATE
    assert "不要複製它的句首、例子或收尾" in CHAT_SYSTEM_TEMPLATE
    assert "我還不知道怎樣才算通過" not in CHAT_SYSTEM_TEMPLATE
    assert "兩者只能選符合本項設定的一種" in CHAT_SYSTEM_TEMPLATE
    assert "不得含糊寫成「由 AI 或導師判斷」" in CHAT_SYSTEM_TEMPLATE
    assert "補充後，我會重新確認並建立提案給你查看" not in CHAT_SYSTEM_TEMPLATE
    assert "`list_checklist` 回傳所有項目的 ID、標題與偵測狀態" in CHAT_SYSTEM_TEMPLATE
    assert "用 ID 查詢單一項目完整內容" in CHAT_SYSTEM_TEMPLATE
    assert "全新、與既有項目無關" in CHAT_SYSTEM_TEMPLATE
    assert "檢查項目提案只能透過 `create_checklist_item`（新增）或" in (
        CHAT_SYSTEM_TEMPLATE
    )
    assert "只填有變動的欄位" in CHAT_SYSTEM_TEMPLATE
    assert "{rubric_context}" not in CHAT_SYSTEM_TEMPLATE
    assert '"proposal_status": "ready | needs_information | unsupported | none"' in (
        CHAT_SYSTEM_TEMPLATE
    )
    assert "success_criteria" not in CHAT_SYSTEM_TEMPLATE
    assert "成功條件" not in CHAT_SYSTEM_TEMPLATE
    assert "你覺得...如何" not in SITUATION_NORMAL


def test_teacher_judge_prompt_uses_goal_directed_diagnostic_principles():
    assert "熟悉 Linux、Windows 系統管理與常見 CLI 工具" in CHAT_SYSTEM_TEMPLATE
    assert "根據老師要確認的目的，自行選擇適合的診斷指令" in (
        CHAT_SYSTEM_TEMPLATE
    )
    assert "優先規劃唯讀、診斷型指令" in CHAT_SYSTEM_TEMPLATE
    assert "能以低權限取得資訊時，不要求 `sudo` 或 Administrator" in (
        CHAT_SYSTEM_TEMPLATE
    )
    assert "避免無目的大量執行指令" in CHAT_SYSTEM_TEMPLATE
    assert "不只回傳原始輸出" in CHAT_SYSTEM_TEMPLATE
    assert "不是提案白名單" in CHAT_SYSTEM_TEMPLATE
    assert "沒有專用項目時使用 command collector" in CHAT_SYSTEM_TEMPLATE
    assert "systemctl list-units" not in CHAT_SYSTEM_TEMPLATE
    assert "journalctl --since" not in CHAT_SYSTEM_TEMPLATE
    assert "`history` 是 shell builtin" not in CHAT_SYSTEM_TEMPLATE


def test_teacher_judge_chat_prompt_caps_structured_payload_size() -> None:
    assert "requirements 最多 4 條" in CHAT_SYSTEM_TEMPLATE
    assert "每條不超過 30 字" in CHAT_SYSTEM_TEMPLATE
    assert "不要用 markdown code block 包住整份 JSON" in CHAT_SYSTEM_TEMPLATE
    assert "不要把結構化欄位重複寫進 reply" in CHAT_SYSTEM_TEMPLATE
