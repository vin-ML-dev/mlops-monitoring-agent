"""Error taxonomy -> stable HTTP responses. Never leak stack traces to clients."""

from __future__ import annotations


class GatewayError(Exception):
    status = 500
    code = "INTERNAL"
    message = "Internal server error."

    def __init__(self, message: str | None = None):
        if message:
            self.message = message
        super().__init__(self.message)


class ValidationFailed(GatewayError):
    status = 422
    code = "INVALID_REQUEST"
    message = "Invalid request."


class AuthFailed(GatewayError):
    status = 401
    code = "UNAUTHORIZED"
    message = "Invalid or missing API key."


class RateLimited(GatewayError):
    status = 429
    code = "RATE_LIMITED"
    message = "Too many requests."

    def __init__(self, retry_after: int | None = None, message: str | None = None):
        self.retry_after = retry_after
        super().__init__(message)


class Overloaded(GatewayError):
    status = 503
    code = "OVERLOADED"
    message = "The service is busy. Please retry shortly."

    def __init__(self, retry_after: int | None = None, message: str | None = None):
        self.retry_after = retry_after
        super().__init__(message)


class BackendUnavailable(GatewayError):
    status = 503
    code = "MODEL_UNAVAILABLE"
    message = "The model is temporarily unavailable."


class BackendTimeout(GatewayError):
    status = 504
    code = "MODEL_TIMEOUT"
    message = "The model took too long to respond."


def to_body(err: GatewayError, request_id: str) -> dict:
    return {"error": {"code": err.code, "message": err.message, "request_id": request_id}}
