import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class BusinessError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        code: str = "BUSINESS_ERROR",
    ):
        self.message = message
        self.status_code = status_code
        self.code = code


class NotFoundError(BusinessError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404, code="NOT_FOUND")


class ValidationError(BusinessError):
    def __init__(self, message: str = "Validation failed"):
        super().__init__(message, status_code=400, code="VALIDATION_ERROR")


class UnauthorizedError(BusinessError):
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, status_code=401, code="UNAUTHORIZED")


class ForbiddenError(BusinessError):
    def __init__(self, message: str = "Forbidden"):
        super().__init__(message, status_code=403, code="FORBIDDEN")


class ConflictError(BusinessError):
    def __init__(self, message: str = "Conflict"):
        super().__init__(message, status_code=409, code="CONFLICT")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BusinessError)
    async def business_error_handler(request: Request, exc: BusinessError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "status": exc.status_code,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.exception("Unhandled request error: %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Internal server error",
                "status": 500,
            },
        )
