"""app/utils/token.py 的密碼重設 token：內嵌 token_version，解碼後可取回 email 與版本號。"""

from app.utils.token import decode_password_reset_token, generate_password_reset_token

# ---------------------------------------------------------------------------
# password reset token is single-use via token_version binding
# ---------------------------------------------------------------------------


def test_password_reset_token_carries_token_version() -> None:
    token = generate_password_reset_token(email="user@example.com", token_version=3)
    assert decode_password_reset_token(token) == ("user@example.com", 3)
