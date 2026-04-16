from __future__ import annotations

import pytest

from app.exceptions import ProxmoxError
from app.infrastructure.proxmox import client as proxmox_client


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
        "get_proxmox_api",
        lambda: _FakeProxmox(
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
