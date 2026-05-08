"""
Auth router — login, password reset, current user.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.security import decode_access_token
from app.db.deps import get_db
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    SendCodeRequest,
    ResetPasswordRequest,
    MessageResponse,
    MeResponse,
)
from app.schemas.super_admin import AdminLoginRequest, AdminLoginResponse, AdminUserInfo
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return JWT token."""
    return await AuthService.login(db, body)


@router.post("/admin-login", response_model=AdminLoginResponse)
async def admin_login(body: AdminLoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate super admin and return JWT token."""
    return await AuthService.admin_login(db, body)


@router.post("/send-verification-code", response_model=MessageResponse)
async def send_verification_code(
    body: SendCodeRequest, db: AsyncSession = Depends(get_db)
):
    """Send a password-reset verification code to the user's email."""
    email = await AuthService.send_verification_code(db, body)
    masked = email[:3] + "***" + email[email.index("@"):]
    return {"message": f"Verification code sent to {masked}"}


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)
):
    """Reset password using verification code."""
    await AuthService.reset_password(db, body)
    return {"message": "Password reset successfully"}


@router.get("/me", response_model=MeResponse)
async def get_current_user(request: Request):
    """Return the current authenticated user from JWT."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid authorization header")

    token = auth_header.split(" ", 1)[1]
    payload = decode_access_token(token)

    return MeResponse(
        id=int(payload["sub"]),
        tenant_id=payload["tenant_id"],
        username=payload["username"],
        role=payload["role"],
    )


@router.get("/admin-me", response_model=AdminUserInfo)
async def get_current_admin(request: Request):
    """Return the current authenticated super admin from JWT."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid authorization header")

    token = auth_header.split(" ", 1)[1]
    payload = decode_access_token(token)

    if payload.get("role") != "super_admin":
        raise UnauthorizedError("Not a super admin")

    return AdminUserInfo(
        id=int(payload["sub"]),
        username=payload["username"],
        role=payload["role"],
    )
