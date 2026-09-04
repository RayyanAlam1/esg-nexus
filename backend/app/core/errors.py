"""Consistent error envelope: {"error": {"code", "message", "details"}}."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    status_code = 400
    code = "app_error"

    def __init__(self, message: str, *, details: Any = None, status_code: int | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class PermissionError_(AppError):
    status_code = 403
    code = "forbidden"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class GovernanceBlockedError(AppError):
    """Raised when a governance rule blocks an action. Details carry the rule and required action."""

    status_code = 422
    code = "governance_blocked"


class GuardrailError(AppError):
    status_code = 422
    code = "guardrail_rejected"


def envelope(code: str, message: str, details: Any = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=envelope(exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content=envelope("validation_error", "Request validation failed", exc.errors()))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content=envelope("http_error", str(exc.detail), None))
