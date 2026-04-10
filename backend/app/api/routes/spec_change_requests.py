import uuid

from fastapi import APIRouter

from app.api.deps import AdminUser, CurrentUser, SessionDep
from app.schemas import (
    SpecChangeRequestCreate,
    SpecChangeRequestPublic,
    SpecChangeRequestReview,
    SpecChangeRequestsPublic,
)
from app.models import SpecChangeRequestStatus
from app.services.vm import spec_change_service

router = APIRouter(prefix="/spec-change-requests", tags=["spec-change-requests"])


@router.post("/", response_model=SpecChangeRequestPublic)
def create_spec_change_request(
    request_in: SpecChangeRequestCreate,
    session: SessionDep,
    current_user: CurrentUser,
):
    return spec_change_service.create(
        session=session, request_in=request_in, user=current_user
    )


@router.get("/my", response_model=SpecChangeRequestsPublic)
def get_my_spec_change_requests(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
):
    return spec_change_service.list_by_user(
        session=session, user_id=current_user.id, skip=skip, limit=limit
    )


@router.get("/", response_model=SpecChangeRequestsPublic)
def get_all_spec_change_requests(
    session: SessionDep,
    current_user: AdminUser,
    skip: int = 0,
    limit: int = 100,
    status: SpecChangeRequestStatus | None = None,
    vmid: int | None = None,
):
    return spec_change_service.list_all(
        session=session, skip=skip, limit=limit, status=status, vmid=vmid
    )


@router.post("/{request_id}/review", response_model=SpecChangeRequestPublic)
def review_spec_change_request(
    request_id: uuid.UUID,
    review: SpecChangeRequestReview,
    session: SessionDep,
    current_user: AdminUser,
):
    return spec_change_service.review(
        session=session,
        request_id=request_id,
        review_data=review,
        reviewer=current_user,
    )
