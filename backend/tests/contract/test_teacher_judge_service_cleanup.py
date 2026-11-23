"""Teacher Judge service cleanup: structural contracts (lazy package import, single PEER_IP_TOKEN definition)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app.ai.teacher_judge import machine_context
from app.ai.teacher_judge import service as teacher_judge_service
from app.ai.teacher_judge.script_policy import PEER_IP_TOKEN

BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_package_init_does_not_eagerly_load_service() -> None:
    code = (
        "import sys\n"
        "import app.ai.teacher_judge.config\n"
        "assert 'app.ai.teacher_judge.service' not in sys.modules\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_peer_ip_token_has_one_definition() -> None:
    assert machine_context.PEER_IP_TOKEN is PEER_IP_TOKEN
    assert teacher_judge_service.PEER_IP_TOKEN is PEER_IP_TOKEN
