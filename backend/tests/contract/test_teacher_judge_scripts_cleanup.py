"""Teacher Judge scripts cleanup: structural contract (PEER_IP_TOKEN has one definition)."""

from __future__ import annotations

from app.ai.teacher_judge import deterministic_compiler, machine_context
from app.ai.teacher_judge.script_policy import PEER_IP_TOKEN


def test_peer_ip_token_has_one_definition() -> None:
    assert PEER_IP_TOKEN == "{{peer.ip}}"
    assert deterministic_compiler.PEER_IP_TOKEN is PEER_IP_TOKEN
    assert machine_context.PEER_IP_TOKEN == PEER_IP_TOKEN
