"""rotate_secret_key must cover every Fernet-encrypted column."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from sqlmodel import SQLModel

from app.core import security
from scripts import rotate_secret_key as rsk

# Registers every table on SQLModel.metadata (import for side effect only).
importlib.import_module("app.models")

# Encrypted columns whose names do not say so.
_UNNAMED_ENCRYPTED = {
    ("web_push_config", "vapid_private_key_pem"),
    ("vm_requests", "password"),
}


def test_encrypted_columns_cover_every_encrypted_model_field() -> None:
    expected = set(_UNNAMED_ENCRYPTED)
    for table in SQLModel.metadata.tables.values():
        for column in table.columns:
            if "encrypted" in column.name:
                expected.add((table.name, column.name))

    covered = {(c.table, c.column) for c in rsk.ENCRYPTED_COLUMNS}
    assert expected - covered == set()


def test_rotate_value_outcomes() -> None:
    old = security.derive_fernet("old-key")
    new = security.derive_fernet("new-key")

    outcome, value = rsk.rotate_value(
        old.encrypt(b"secret").decode(), old_fernet=old, new_fernet=new
    )
    assert outcome == "rotated"
    assert value is not None and new.decrypt(value.encode()) == b"secret"

    already = new.encrypt(b"secret").decode()
    assert rsk.rotate_value(already, old_fernet=old, new_fernet=new) == (
        "skipped",
        None,
    )

    lost = security.derive_fernet("other-key").encrypt(b"secret").decode()
    assert rsk.rotate_value(lost, old_fernet=old, new_fernet=new) == (
        "failed",
        None,
    )


def test_rotate_value_encrypts_legacy_plaintext_pem() -> None:
    old = security.derive_fernet("old-key")
    new = security.derive_fernet("new-key")
    pem = "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n"

    outcome, value = rsk.rotate_value(
        pem, old_fernet=old, new_fernet=new, legacy_plaintext_pem=True
    )

    assert outcome == "rotated"
    assert value is not None and new.decrypt(value.encode()).decode() == pem

    # Only the flagged column (web_push_config) may hold legacy plaintext.
    assert rsk.rotate_value(pem, old_fernet=old, new_fernet=new) == (
        "failed",
        None,
    )
    vapid = next(
        c for c in rsk.ENCRYPTED_COLUMNS if c.table == "web_push_config"
    )
    assert vapid.legacy_plaintext_pem


def test_load_json_payload_accepts_json_and_legacy_text_columns() -> None:
    payload = {"login_password_enc": "x"}
    assert rsk._load_json_payload(payload) == payload
    assert rsk._load_json_payload(json.dumps(payload)) == payload
    assert rsk._load_json_payload("not json") is None
    assert rsk._load_json_payload("[1]") is None
    assert rsk._load_json_payload(None) is None


def test_json_assignment_casts_to_the_column_type() -> None:
    assert rsk._json_assignment("JSON") == "CAST(:value AS json)"
    assert rsk._json_assignment("JSONB") == "CAST(:value AS jsonb)"
    assert rsk._json_assignment("TEXT") == ":value"


def test_find_env_file_rejects_missing_file_or_key_line(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        rsk.find_env_file(str(tmp_path / "missing.env"))

    no_key = tmp_path / "no_key.env"
    no_key.write_text("DOMAIN=example.com\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        rsk.find_env_file(str(no_key))

    ok = tmp_path / "ok.env"
    ok.write_text("SECRET_KEY=old\n", encoding="utf-8")
    assert rsk.find_env_file(str(ok)) == ok


def test_write_secret_key_keeps_other_lines_and_literal_backslashes(
    tmp_path: Path,
) -> None:
    env = tmp_path / ".env"
    env.write_text("DOMAIN=x\nSECRET_KEY=old\nOTHER=y\n", encoding="utf-8")

    rsk.write_secret_key(env, r"new\1key\g<0>")

    assert env.read_text(encoding="utf-8") == (
        "DOMAIN=x\nSECRET_KEY=new\\1key\\g<0>\nOTHER=y\n"
    )
    assert (tmp_path / ".env.bak").read_text(encoding="utf-8").count("old") == 1


def test_write_secret_key_replaces_every_secret_key_line(tmp_path: Path) -> None:
    # dotenv / Compose 以最後一行為準；只改第一行會讓舊金鑰繼續生效。
    env = tmp_path / ".env"
    env.write_text(
        "SECRET_KEY=changethis\nDOMAIN=x\nSECRET_KEY=old\n", encoding="utf-8"
    )

    rsk.write_secret_key(env, "new-key")

    assert env.read_text(encoding="utf-8") == (
        "SECRET_KEY=new-key\nDOMAIN=x\nSECRET_KEY=new-key\n"
    )
