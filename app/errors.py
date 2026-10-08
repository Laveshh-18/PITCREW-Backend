class ApiError(Exception):
    """Raised anywhere; main.py turns it into the Section 8.3 error format."""

    def __init__(self, status: int, code: str, message: str, details: dict | None = None,
                 headers: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.details, self.headers = details or {}, headers or {}


def bad(code: str, message: str, status: int = 422, **details) -> ApiError:
    return ApiError(status, code, message, details)
