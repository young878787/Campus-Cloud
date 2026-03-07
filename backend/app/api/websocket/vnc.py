import asyncio
import logging
import ssl
from urllib.parse import quote

import websockets
from fastapi import WebSocket, WebSocketDisconnect

from app.api.deps.auth import get_ws_current_user
from app.api.deps.proxmox import check_resource_ownership
from app.core.config import settings
from app.exceptions import NotFoundError, ProxmoxError
from app.services import proxmox_service

logger = logging.getLogger(__name__)


async def vnc_proxy(websocket: WebSocket, vmid: int, token: str):
    """WebSocket proxy for VM VNC console access."""
    # Authenticate user and check ownership before accepting
    user, session = await get_ws_current_user(websocket, token=token)
    try:
        check_resource_ownership(vmid, user, session)
    except Exception:
        await websocket.close(code=1008, reason="Permission denied")
        return

    await websocket.accept()
    logger.info(f"VNC proxy connection for VM {vmid} by user {user.email}")

    pve_websocket = None

    try:
        # Get session ticket (password-based, required for PVE WebSocket)
        try:
            pve_auth_cookie, _ = await proxmox_service.get_session_ticket()
        except ProxmoxError:
            logger.error("Proxmox session authentication failed")
            await websocket.close(code=1008, reason="Authentication failed")
            return

        logger.info("Retrieved session ticket for VNC WebSocket authentication")

        # Find VM in cluster resources
        try:
            vm_info = proxmox_service.find_resource(vmid)
        except NotFoundError:
            logger.error(f"VM {vmid} not found in cluster")
            await websocket.close(code=1008, reason="VM not found")
            return

        node = vm_info["node"]
        logger.info(
            f"VM {vmid} found on node {node}, status: {vm_info.get('status', 'unknown')}"
        )

        # Get VNC proxy ticket
        console_data = proxmox_service.get_vnc_ticket(node, vmid)
        vnc_port = console_data["port"]
        vnc_ticket = console_data["ticket"]

        encoded_vnc_ticket = quote(vnc_ticket, safe="")
        encoded_auth_cookie = quote(pve_auth_cookie, safe="")

        # WebSocket URL for VNC
        pve_ws_url = (
            f"wss://{settings.PROXMOX_HOST}:8006"
            f"/api2/json/nodes/{node}/qemu/{vmid}/vncwebsocket"
            f"?port={vnc_port}&vncticket={encoded_vnc_ticket}"
        )

        ssl_context = ssl.create_default_context()
        if not settings.PROXMOX_VERIFY_SSL:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        try:
            # Use Cookie with session ticket
            pve_websocket = await websockets.connect(
                pve_ws_url,
                ssl=ssl_context,
                additional_headers={"Cookie": f"PVEAuthCookie={encoded_auth_cookie}"},
                max_size=2**20,
            )
            logger.info("Successfully connected to Proxmox VNC WebSocket")
        except websockets.exceptions.InvalidStatus as e:
            logger.error(
                f"Proxmox WebSocket connection rejected: HTTP {e.response.status_code}"
            )
            await websocket.close(code=1008, reason="Proxmox connection failed")
            return

        logger.info(f"WebSocket proxy established for VM {vmid}")

        async def forward_from_proxmox():
            try:
                async for message in pve_websocket:
                    try:
                        if isinstance(message, bytes):
                            await websocket.send_bytes(message)
                        else:
                            await websocket.send_text(message)
                    except Exception:
                        break
            except websockets.exceptions.ConnectionClosed:
                pass
            except Exception as e:
                logger.error(f"Error forwarding from Proxmox: {e}")

        async def forward_to_proxmox():
            try:
                while True:
                    data = await websocket.receive()
                    if data.get("type") == "websocket.disconnect":
                        break
                    if "bytes" in data:
                        await pve_websocket.send(data["bytes"])
                    elif "text" in data:
                        await pve_websocket.send(data["text"])
            except WebSocketDisconnect:
                pass
            except Exception as e:
                logger.error(f"Error forwarding to Proxmox: {e}")

        # Run both directions concurrently; first to finish cancels the other
        await asyncio.gather(
            forward_from_proxmox(),
            forward_to_proxmox(),
            return_exceptions=True,
        )

    except Exception as e:
        logger.error(f"Failed to establish WebSocket proxy: {e}", exc_info=True)
        await websocket.close(code=1011, reason=str(e))
    finally:
        if pve_websocket:
            await pve_websocket.close()
        logger.info(f"VNC proxy disconnected for VM {vmid}")
