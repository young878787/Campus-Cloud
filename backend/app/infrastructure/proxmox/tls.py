from __future__ import annotations

import socket
import ssl

from app.exceptions import ProxmoxError
from app.infrastructure.proxmox.settings import ProxmoxSettings

_TCP_PING_TIMEOUT = 2.0


def _tcp_ping(host: str, port: int = 8006, timeout: float = _TCP_PING_TIMEOUT) -> bool:
    """Use TCP connect instead of ICMP to quickly verify host reachability."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, ConnectionRefusedError, OSError):
        return False


def _verify_server_with_ca(host: str, ca_cert_pem: str, port: int = 8006) -> None:
    """Validate a Proxmox node certificate against the configured CA."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cadata=ca_cert_pem)

    if hasattr(ssl, "VERIFY_X509_STRICT"):
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT

    try:
        with socket.create_connection((host, port), timeout=10) as raw_sock:
            with ctx.wrap_socket(raw_sock, server_hostname=host):
                pass
    except ssl.SSLCertVerificationError as exc:
        raise ProxmoxError(f"CA certificate verification failed: {exc}") from exc
    except (TimeoutError, ConnectionRefusedError, OSError) as exc:
        raise ProxmoxError(
            f"Unable to connect to Proxmox host {host}:{port}: {exc}"
        ) from exc


def build_ws_ssl_context(cfg: ProxmoxSettings) -> ssl.SSLContext:
    """Create an SSL context suitable for VNC/terminal websocket handshakes."""
    if cfg.ca_cert:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_verify_locations(cadata=cfg.ca_cert)
        if hasattr(ssl, "VERIFY_X509_STRICT"):
            ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
        return ctx

    if cfg.verify_ssl:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_default_certs()
        return ctx

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx
