"""
Auth request/response schemas.
"""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    tenant: str = Field(..., min_length=2, max_length=64)
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=72)


class LoginResponse(BaseModel):
    token: str
    user: "LoginUserInfo"


class LoginUserInfo(BaseModel):
    id: int
    tenant_id: str
    username: str
    role: str


class SendCodeRequest(BaseModel):
    tenant: str = Field(..., min_length=2, max_length=64)
    username: str = Field(..., min_length=1, max_length=64)
    locale: str = Field(default="zh")


class ResetPasswordRequest(BaseModel):
    tenant: str = Field(..., min_length=2, max_length=64)
    username: str = Field(..., min_length=1, max_length=64)
    verify_code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8, max_length=72)


class MessageResponse(BaseModel):
    message: str


class MeResponse(BaseModel):
    id: int
    tenant_id: str
    username: str
    role: str
