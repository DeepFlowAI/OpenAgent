"""
Super admin request/response schemas.
"""
from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=72)


class AdminLoginResponse(BaseModel):
    token: str
    user: "AdminUserInfo"


class AdminUserInfo(BaseModel):
    id: int
    username: str
    role: str
