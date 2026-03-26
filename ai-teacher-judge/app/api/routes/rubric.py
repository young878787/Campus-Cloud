from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File, Request
from fastapi.responses import Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.schemas.rubric import RubricChatRequest
from app.services.rubric_parser import parse_document
from app.services.rubric_service import (
    analyze_rubric,
    chat_with_rubric,
    export_to_excel,
    normalize_items_for_export,
)

router = APIRouter(tags=["rubric"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/upload-rubric")
@router.post("/api/v1/upload-rubric")
@limiter.limit("10/minute")  # 每分鐘最多 10 次上傳
async def upload_rubric(request: Request, file: UploadFile = File(...)):
    """上傳評分表文件（.docx / .pdf），AI 解析並回傳結構化評分分析。"""
    from app.core.config import settings
    
    filename = file.filename or "unknown"
    allowed = {".docx", ".pdf"}
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in allowed:
        raise HTTPException(
            status_code=415,
            detail=f"不支援的格式 '{suffix}'，目前接受：{', '.join(allowed)}",
        )

    file_bytes = await file.read()
    
    # 檔案大小檢查
    file_size_mb = len(file_bytes) / (1024 * 1024)
    if len(file_bytes) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413, 
            detail=f"檔案大小 {file_size_mb:.1f}MB 超過限制（最大 {settings.max_upload_size_mb}MB）"
        )
    
    if not file_bytes:
        raise HTTPException(status_code=400, detail="上傳的檔案是空的。")

    try:
        raw_text = parse_document(filename, file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    if not raw_text.strip():
        raise HTTPException(status_code=422, detail="無法從文件中提取任何文字，請確認文件不是掃描版 PDF。")

    analysis, metrics = await analyze_rubric(raw_text)
    return {
        "analysis": analysis.model_dump(),
        "ai_metrics": metrics,
    }


@router.post("/chat")
@router.post("/api/v1/chat")
@limiter.limit("30/minute")  # 每分鐘最多 30 次對話
async def chat(request: Request, chat_request: RubricChatRequest):
    """與 AI 對話，精煉評分表；rubric_context 帶入目前評分表的 JSON 字串。"""
    reply, updated_items, metrics = await chat_with_rubric(
        chat_request.messages,
        chat_request.rubric_context,
        is_refine=chat_request.is_refine,
    )
    return {
        "reply": reply,
        "updated_items": updated_items,  # None 或更新後的完整 item 列表
        "prompt_tokens": metrics["prompt_tokens"],
        "completion_tokens": metrics["completion_tokens"],
        "total_tokens": metrics["total_tokens"],
        "elapsed_seconds": metrics["elapsed_seconds"],
        "tokens_per_second": metrics["tokens_per_second"],
    }


@router.post("/download-excel")
@router.post("/api/v1/download-excel")
@limiter.limit("20/minute")  # 每分鐘最多 20 次下載
async def download_excel(request: Request, payload: dict):
    """
    接收 { items: [...RubricItem], summary: str }，
    產出並回傳 .xlsx 檔案。
    """
    raw_items = payload.get("items") or []
    summary = str(payload.get("summary") or "")

    items = normalize_items_for_export(raw_items)

    if not items:
        raise HTTPException(status_code=400, detail="沒有可匯出的評分項目。")

    excel_bytes = export_to_excel(items, summary=summary)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=rubric.xlsx"},
    )
