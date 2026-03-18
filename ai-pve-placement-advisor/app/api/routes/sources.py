from __future__ import annotations

from fastapi import APIRouter

from app.schemas import SourcePreviewResponse
from app.services.analytics_service import build_source_preview


router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/preview", response_model=SourcePreviewResponse)
async def preview_sources():
    return await build_source_preview()
