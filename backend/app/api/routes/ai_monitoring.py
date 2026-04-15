"""
AI Monitoring Routes — Admin 全局 AI 使用監控

掛載在 /ai-api/monitoring/ 前綴下
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, SessionDep
from app.schemas.ai_monitoring import (
    AIMonitoringStats,
    AIProxyCallsResponse,
    AITemplateCallsResponse,
    AIUsersUsageResponse,
)
from app.services.llm_gateway import ai_gateway_service

router = APIRouter(prefix="/ai-api/monitoring", tags=["ai-monitoring"])


@router.get(
    "/stats",
    response_model=AIMonitoringStats,
    summary="全局 AI 統計卡片",
)
def get_stats(
    session: SessionDep,
    current_user: AdminUser,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
):
    """全局 AI 使用統計（Admin only）"""
    return ai_gateway_service.get_monitoring_stats(
        session=session,
        start_date=start_date,
        end_date=end_date,
    )


@router.get(
    "/api-calls",
    response_model=AIProxyCallsResponse,
    summary="Proxy 呼叫清單",
)
def list_api_calls(
    session: SessionDep,
    current_user: AdminUser,
    user_id: uuid.UUID | None = None,
    model_name: str | None = Query(default=None, max_length=255),
    status: str | None = Query(default=None, max_length=50),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    """列出所有 Proxy 呼叫紀錄，支援篩選（Admin only）"""
    return ai_gateway_service.list_proxy_calls(
        session=session,
        user_id=user_id,
        model_name=model_name,
        call_status=status,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/template-calls",
    response_model=AITemplateCallsResponse,
    summary="Template 呼叫清單",
)
def list_template_calls(
    session: SessionDep,
    current_user: AdminUser,
    user_id: uuid.UUID | None = None,
    call_type: str | None = Query(default=None, max_length=30),
    preset: str | None = Query(default=None, max_length=50),
    status: str | None = Query(default=None, max_length=50),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    """列出所有 Template 呼叫紀錄，支援篩選（Admin only）"""
    return ai_gateway_service.list_template_calls(
        session=session,
        user_id=user_id,
        call_type=call_type,
        preset=preset,
        call_status=status,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/users",
    response_model=AIUsersUsageResponse,
    summary="使用者用量彙總",
)
def list_users_usage(
    session: SessionDep,
    current_user: AdminUser,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    """每個使用者的 AI 用量彙總（Admin only）"""
    return ai_gateway_service.list_users_usage(
        session=session,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit,
    )
