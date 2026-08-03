class CommandLogError(Exception):
    """Base exception for expected CommandLog application errors."""

    status_code = 500
    error_code = "internal_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

class UnauthorizedError(CommandLogError):
    status_code = 401
    error_code = "unauthorized"

class ValidationError(CommandLogError):
    status_code = 400
    error_code = "valiation_error"

class NotFoundError(CommandLogError):
    status_code = 404
    error_code = "not_found"

class ConflictError(CommandLogError):
    status_code = 409
    error_code = "conflict"