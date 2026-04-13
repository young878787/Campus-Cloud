"""Tunnel proxy API — provides frpc visitor config to desktop clients."""

import logging

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.services.network import tunnel_proxy_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tunnel", tags=["tunnel"])


@router.get("/my-config")
def get_my_tunnel_config(session: SessionDep, current_user: CurrentUser) -> dict:
    """Return the frpc visitor configuration for the current user.

    The desktop client calls this after login to know which STCP visitors
    to create (one per VM per service).
    Also triggers a Gateway frpc sync to ensure IPs are up-to-date.
    """
    # Best-effort sync so newly created VMs get their IPs resolved
    try:
        tunnel_proxy_service.sync_gateway_frpc(session=session)
    except Exception:
        logger.warning("Failed to sync Gateway frpc during my-config", exc_info=True)

    return tunnel_proxy_service.get_visitor_config_for_user(
        session=session, user_id=current_user.id
    )
