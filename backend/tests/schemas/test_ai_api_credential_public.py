"""app/schemas/ai_api.py 的 AIAPICredentialPublic：對外 schema 不得帶出金鑰明文欄位。"""

from __future__ import annotations


def test_credential_public_never_carries_the_plaintext_key() -> None:
    from app.schemas import AIAPICredentialPublic

    assert "api_key" not in AIAPICredentialPublic.model_fields
