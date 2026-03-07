import uuid

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, CurrentUser, SessionDep
from app.schemas import (
    VMRequestCreate,
    VMRequestPublic,
    VMRequestReview,
    VMRequestsPublic,
)
from app.models import VMRequestStatus
from app.services import vm_request_service

router = APIRouter(prefix="/vm-requests", tags=["vm-requests"])


@router.post("/", response_model=VMRequestPublic)
def create_vm_request(
    request_in: VMRequestCreate, session: SessionDep, current_user: CurrentUser
):
    return vm_request_service.create(
        session=session, request_in=request_in, user=current_user
    )


@router.get("/my", response_model=VMRequestsPublic)
def list_my_vm_requests(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
):
    return vm_request_service.list_by_user(
        session=session, user_id=current_user.id, skip=skip, limit=limit
    )


@router.get("/", response_model=VMRequestsPublic)
def list_all_vm_requests(
    session: SessionDep,
    current_user: AdminUser,
    status: VMRequestStatus | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
):
    return vm_request_service.list_all(
        session=session, status=status, skip=skip, limit=limit
    )


@router.get("/{request_id}", response_model=VMRequestPublic)
def get_vm_request(
    request_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
):
    return vm_request_service.get(
        session=session, request_id=request_id, current_user=current_user
    )


@router.post("/{request_id}/review", response_model=VMRequestPublic)
def review_vm_request(
    request_id: uuid.UUID,
    review: VMRequestReview,
    session: SessionDep,
    current_user: AdminUser,
):
    return vm_request_service.review(
        session=session,
        request_id=request_id,
        review_data=review,
        reviewer=current_user,
    )
