"""AI 對話 API 的資料模型"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """POST /api/v1/chat 請求體"""

    message: str = Field(
        description="使用者輸入的自然語言問題", min_length=1, max_length=2000
    )


class ToolCallRecord(BaseModel):
    """記錄一次工具呼叫的名稱與參數"""

    name: str = Field(description="工具名稱")
    args: dict[str, Any] = Field(default_factory=dict, description="傳入的參數")


class ChatResponse(BaseModel):
    """POST /api/v1/chat 回應體"""

    reply: str = Field(description="AI 的自然語言回答")
    tools_called: list[ToolCallRecord] = Field(
        default_factory=list, description="本次呼叫用到的工具清單（依呼叫順序）"
    )
    error: str | None = Field(default=None, description="若發生錯誤則填入錯誤訊息")
