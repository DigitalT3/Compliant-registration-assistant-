"""Typed API errors rendered as a consistent ``{error:{code,message,request_id}}`` envelope."""


class ApiError(Exception):
    """Controlled, user-safe error with an HTTP status and machine-readable code."""

    def __init__(self, status: int, code: str, message: str, details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details
