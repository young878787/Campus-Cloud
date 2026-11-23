from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from app.exceptions import ProxmoxError
from app.infrastructure.proxmox import client as proxmox_client


@pytest.fixture(autouse=True)
def _reset_client_state():
    proxmox_client.invalidate_proxmox_client()
    yield
    proxmox_client.invalidate_proxmox_client()


class _FakeTaskLog:
    def __init__(self, entries):
        self._entries = entries

    def get(self):
        return self._entries


class _FakeTaskStatus:
    def __init__(self, payload):
        self._payload = payload

    def get(self):
        return self._payload


class _FakeTask:
    def __init__(self, payload, log_entries):
        self.status = _FakeTaskStatus(payload)
        self.log = _FakeTaskLog(log_entries)


class _FakeTasks:
    def __init__(self, payload, log_entries):
        self._payload = payload
        self._log_entries = log_entries

    def __call__(self, _task_id):
        return _FakeTask(self._payload, self._log_entries)


class _FakeNode:
    def __init__(self, payload, log_entries):
        self.tasks = _FakeTasks(payload, log_entries)


class _FakeNodes:
    def __init__(self, payload, log_entries):
        self._payload = payload
        self._log_entries = log_entries

    def __call__(self, _node_name):
        return _FakeNode(self._payload, self._log_entries)


class _FakeProxmox:
    def __init__(self, payload, log_entries):
        self.nodes = _FakeNodes(payload, log_entries)


def test_basic_blocking_task_status_includes_task_log_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        proxmox_client,
        "get_proxmox_api_for_node",
        lambda _node: _FakeProxmox(
            {"status": "stopped", "exitstatus": "terminated"},
            [
                {"t": "migration start"},
                {"t": "ERROR: migration aborted by remote task"},
            ],
        ),
    )

    with pytest.raises(ProxmoxError) as exc_info:
        proxmox_client.basic_blocking_task_status(
            "pve-a",
            "UPID:test",
            check_interval=0,
        )

    message = str(exc_info.value)
    assert "terminated" in message
    assert "migration aborted by remote task" in message


def test_failed_probe_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    nodes = [
        SimpleNamespace(id=1, name="pve-a", host="10.0.0.1", port=8006),
        SimpleNamespace(id=2, name="pve-b", host="10.0.0.2", port=8006),
    ]
    pinged: list[str] = []
    monkeypatch.setattr(
        proxmox_client,
        "get_proxmox_settings",
        lambda _connection_id=None: SimpleNamespace(
            connection_id=None, connection_name=None, host="10.0.0.1"
        ),
    )
    monkeypatch.setattr(proxmox_client, "get_nodes_for_ha", lambda _cid=None: nodes)
    monkeypatch.setattr(
        proxmox_client,
        "_tcp_ping",
        lambda host, _port: pinged.append(host) or False,
    )
    monkeypatch.setattr(proxmox_client, "update_node_online", lambda *_args: None)

    with pytest.raises(ProxmoxError):
        proxmox_client.get_proxmox_api()
    with pytest.raises(ProxmoxError, match="temporarily unavailable"):
        proxmox_client.get_proxmox_api()

    assert pinged == ["10.0.0.1", "10.0.0.2"]


def test_concurrent_callers_share_one_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = object()
    probes = 0

    def connect(_connection_id=None):
        nonlocal probes
        probes += 1
        return fake_client, "pve-a"

    monkeypatch.setattr(proxmox_client, "_connect_proxmox", connect)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _i: proxmox_client.get_proxmox_api(), range(2)))

    assert results == [fake_client, fake_client]
    assert probes == 1
