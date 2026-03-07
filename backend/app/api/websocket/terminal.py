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


async def terminal_proxy(websocket: WebSocket, vmid: int, token: str):
    """WebSocket proxy for LXC container terminal access."""
    # Authenticate user and check ownership before accepting
    user, session = await get_ws_current_user(websocket, token=token)
    try:
        check_resource_ownership(vmid, user, session)
    except Exception:
        await websocket.close(code=1008, reason="Permission denied")
        return

    await websocket.accept()
    logger.info(f"Terminal proxy connection for LXC {vmid} by user {user.email}")

    pve_websocket = None

    try:
        # Get session ticket (password-based, required for PVE WebSocket)
        try:
            pve_auth_cookie, _ = await proxmox_service.get_session_ticket()
        except ProxmoxError:
            logger.error("Proxmox session authentication failed")
            await websocket.close(code=1008, reason="Authentication failed")
            return

        logger.info("Retrieved session ticket for WebSocket authentication")

        # Find LXC container in cluster resources
        try:
            container_info = proxmox_service.find_lxc(vmid)
        except NotFoundError:
            logger.error(f"LXC container {vmid} not found in cluster")
            await websocket.close(code=1008, reason="LXC container not found")
            return

        node = container_info["node"]
        logger.info(
            f"LXC container {vmid} found on node {node}, status: {container_info.get('status', 'unknown')}"
        )

        # Get terminal proxy ticket
        console_data = proxmox_service.get_terminal_ticket(node, vmid)
        terminal_port = console_data["port"]
        terminal_ticket = console_data["ticket"]

        encoded_terminal_ticket = quote(terminal_ticket, safe="")
        encoded_auth_cookie = quote(pve_auth_cookie, safe="")

        # WebSocket URL for terminal (using vncwebsocket endpoint for termproxy)
        pve_ws_url = (
            f"wss://{settings.PROXMOX_HOST}:8006"
            f"/api2/json/nodes/{node}/lxc/{vmid}/vncwebsocket"
            f"?port={terminal_port}&vncticket={encoded_terminal_ticket}"
        )

        ssl_context = ssl.create_default_context()
        if not settings.PROXMOX_VERIFY_SSL:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        try:
            # Use Cookie with session ticket (NOT API token!)
            pve_websocket = await websockets.connect(
                pve_ws_url,
                ssl=ssl_context,
                additional_headers={"Cookie": f"PVEAuthCookie={encoded_auth_cookie}"},
                max_size=2**20,
            )
            logger.info("Successfully connected to Proxmox WebSocket for terminal")

            # Send initial authentication to termproxy
            # Format: username:ticket\n (newline is critical!)
            auth_message = f"{settings.PROXMOX_USER}:{terminal_ticket}\n"
            await pve_websocket.send(auth_message)
            logger.info("Sent authentication to termproxy")

        except websockets.exceptions.InvalidStatus as e:
            logger.error(
                f"Proxmox WebSocket connection rejected: HTTP {e.response.status_code}"
            )
            await websocket.close(code=1008, reason="Proxmox connection failed")
            return

        logger.info(f"WebSocket proxy established for LXC {vmid}")

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
        logger.info(f"Terminal proxy disconnected for LXC {vmid}")
