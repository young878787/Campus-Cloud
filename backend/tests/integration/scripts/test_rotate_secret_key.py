"""rotate_secret_key 需真 DB 的整合測試：user 表（保留字）與 task_records JSON payload 一併輪替。"""

from __future__ import annotations

import uuid

import pytest
from sqlmodel import Session

from app.core import security
from app.core.config import settings
from app.models.task_record import TaskRecord
from scripts import rotate_secret_key as rsk
from tests.utils.user import create_random_user


def test_rotate_round_trip_on_user_table_and_task_payload(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``user`` is a reserved word: the generated SQL must quote it."""
    user = create_random_user(db)
    user.totp_secret_encrypted = security.encrypt_value("JBSWY3DPEHPK3PXP")
    db.add(user)
    record = TaskRecord(
        id=uuid.uuid4(),
        task_type="b16_rotate_test",
        user_id=user.id,
        payload={"hostname": "h", "login_password_enc": security.encrypt_value("pw")},
    )
    db.add(record)
    db.commit()

    monkeypatch.setattr(
        rsk,
        "ENCRYPTED_COLUMNS",
        (rsk.EncryptedColumn("user", "id", "totp_secret_encrypted"),),
    )
    original_key = settings.SECRET_KEY
    new_key = "test-rotated-secret-key"
    new_fernet = security.derive_fernet(new_key)

    try:
        assert rsk.rotate(new_key=new_key, apply=True, skip_undecryptable=True) == 0

        db.expire_all()
        user_row = db.get(type(user), user.id)
        assert user_row is not None and user_row.totp_secret_encrypted
        assert (
            new_fernet.decrypt(user_row.totp_secret_encrypted.encode()).decode()
            == "JBSWY3DPEHPK3PXP"
        )
        task_row = db.get(TaskRecord, record.id)
        assert task_row is not None
        # task_records.payload is a json column (dbm06): it must stay an object.
        payload = task_row.payload
        assert isinstance(payload, dict)
        assert payload["hostname"] == "h"
        assert new_fernet.decrypt(payload["login_password_enc"].encode()) == b"pw"
    finally:
        # Rotate back so the rest of the suite still decrypts with the test key.
        monkeypatch.setattr(settings, "SECRET_KEY", new_key)
        rsk.rotate(new_key=original_key, apply=True, skip_undecryptable=True)
        monkeypatch.setattr(settings, "SECRET_KEY", original_key)
        db.expire_all()
        task_row = db.get(TaskRecord, record.id)
        if task_row is not None:
            db.delete(task_row)
        user_row = db.get(type(user), user.id)
        if user_row is not None:
            db.delete(user_row)
        db.commit()

    assert security.decrypt_value(
        security.encrypt_value("x")
    ) == "x"
