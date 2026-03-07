"""通用 schemas：Token、Message 等"""

from pydantic import BaseModel, Field


class Message(BaseModel):
    """通用訊息回應"""

    message: str


class Token(BaseModel):
    """JWT 存取權杖回應"""

    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """JWT Token payload"""

    sub: str | None = None


class NewPassword(BaseModel):
    """重設密碼請求"""

    token: str
    new_password: str = Field(min_length=8, max_length=128)
