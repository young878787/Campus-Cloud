"""Gateway VM 管理服務."""

from __future__ import annotations

import logging

from app.exceptions import BadRequestError, ProxmoxError
from app.infrastructure.ssh import (
    SSHAuthenticationError,
    create_key_client,
    exec_command,
    generate_ed25519_keypair as _generate_ed25519_keypair,
)

logger = logging.getLogger(__name__)

SERVICE_CONFIG_PATHS: dict[str, str] = {
    "haproxy": "/etc/haproxy/haproxy.cfg",
    "traefik": "/etc/traefik/traefik.yml",
    "frps": "/etc/frp/frps.toml",
    "frpc": "/etc/frp/frpc.toml",
}

TRAEFIK_DYNAMIC_PATH = "/etc/traefik/dynamic/campus-cloud.yml"


def generate_ed25519_keypair() -> tuple[str, str]:
    return _generate_ed25519_keypair()


def _make_client(host: str, ssh_port: int, ssh_user: str, private_key_pem: str):
    return create_key_client(
        host,
        ssh_port,
        ssh_user,
        private_key_pem,
        timeout=10,
        host_key_policy="auto_add",
    )


def _exec(client, command: str) -> tuple[int, str, str]:
    return exec_command(client, command)


def _get_config(session: object) -> object:
    from app.repositories import gateway_config as gw_repo  # noqa: PLC0415

    config = gw_repo.get_gateway_config(session)  # type: ignore[arg-type]
    if config is None or not config.host or not config.encrypted_private_key:
        raise BadRequestError("Gateway VM 尚未設定，請先設定 IP 並生成 SSH 金鑰")
    return config


def test_connection(
    host: str,
    ssh_port: int,
    ssh_user: str,
    private_key_pem: str,
) -> tuple[bool, str]:
    try:
        client = _make_client(host, ssh_port, ssh_user, private_key_pem)
        _, out, _ = _exec(client, "echo ok")
        client.close()
        if out.strip() == "ok":
            return True, "連線成功"
        return False, f"指令回應異常：{out}"
    except SSHAuthenticationError:
        return False, "SSH 認證失敗，請確認公鑰已加入 Gateway VM 的 authorized_keys"
    except Exception as exc:
        return False, f"連線失敗：{exc}"


def read_service_config(session: object, service: str) -> str:
    from app.repositories.gateway_config import get_decrypted_private_key  # noqa: PLC0415

    config = _get_config(session)
    private_key_pem = get_decrypted_private_key(config)  # type: ignore[arg-type]

    path = SERVICE_CONFIG_PATHS.get(service)
    if path is None:
        raise BadRequestError(f"未知服務：{service}")

    client = _make_client(config.host, config.ssh_port, config.ssh_user, private_key_pem)
    try:
        sftp = client.open_sftp()
        try:
            try:
                with sftp.open(path, "r") as handle:
                    return handle.read().decode()
            except FileNotFoundError:
                return ""
        finally:
            sftp.close()
    except Exception as exc:
        raise ProxmoxError(f"讀取 {service} 設定失敗：{exc}")
    finally:
        client.close()


def write_service_config(session: object, service: str, content: str) -> None:
    from app.repositories.gateway_config import get_decrypted_private_key  # noqa: PLC0415

    config = _get_config(session)
    private_key_pem = get_decrypted_private_key(config)  # type: ignore[arg-type]

    path = SERVICE_CONFIG_PATHS.get(service)
    if path is None:
        raise BadRequestError(f"未知服務：{service}")

    client = _make_client(config.host, config.ssh_port, config.ssh_user, private_key_pem)
    try:
        sftp = client.open_sftp()
        try:
            tmp_path = path + ".tmp"
            with sftp.open(tmp_path, "w") as handle:
                handle.write(content.encode())
        finally:
            sftp.close()

        code, _, err = _exec(client, f"mv {tmp_path} {path}")
        if code != 0:
            raise ProxmoxError(f"寫入 {service} 設定失敗：{err}")
    except ProxmoxError:
        raise
    except Exception as exc:
        raise ProxmoxError(f"寫入 {service} 設定失敗：{exc}")
    finally:
        client.close()


def control_service(session: object, service: str, action: str) -> tuple[bool, str]:
    from app.repositories.gateway_config import get_decrypted_private_key  # noqa: PLC0415

    config = _get_config(session)
    private_key_pem = get_decrypted_private_key(config)  # type: ignore[arg-type]

    valid_actions = {"start", "stop", "restart", "reload"}
    if action not in valid_actions:
        raise BadRequestError(f"無效操作：{action}")

    if service not in SERVICE_CONFIG_PATHS:
        raise BadRequestError(f"未知服務：{service}")

    try:
        client = _make_client(config.host, config.ssh_port, config.ssh_user, private_key_pem)
        code, out, err = _exec(client, f"systemctl {action} {service} 2>&1")
        client.close()
        output = (out + err).strip()
        return code == 0, output or f"{service} {action} 完成"
    except Exception as exc:
        return False, str(exc)


def get_service_status(session: object, service: str) -> tuple[bool, str]:
    from app.repositories.gateway_config import get_decrypted_private_key  # noqa: PLC0415

    config = _get_config(session)
    private_key_pem = get_decrypted_private_key(config)  # type: ignore[arg-type]

    if service not in SERVICE_CONFIG_PATHS:
        raise BadRequestError(f"未知服務：{service}")

    try:
        client = _make_client(config.host, config.ssh_port, config.ssh_user, private_key_pem)
        code, _, _ = _exec(client, f"systemctl is-active {service}")
        _, status_out, _ = _exec(
            client,
            f"systemctl show {service} --no-page "
            f"-p ActiveState,SubState,MainPID 2>&1 | head -5",
        )
        client.close()
        return code == 0, status_out.strip()
    except Exception as exc:
        return False, str(exc)
