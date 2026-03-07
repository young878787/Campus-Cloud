"""Application-level exceptions for the service layer."""


class AppError(Exception):
    """Base application error."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, message: str = "Not found"):
        super().__init__(message, 404)


class PermissionDeniedError(AppError):
    def __init__(self, message: str = "Permission denied"):
        super().__init__(message, 403)


class ConflictError(AppError):
    def __init__(self, message: str = "Conflict"):
        super().__init__(message, 409)


class BadRequestError(AppError):
    def __init__(self, message: str = "Bad request"):
        super().__init__(message, 400)


class ProvisioningError(AppError):
    def __init__(self, message: str = "Provisioning failed"):
        super().__init__(message, 500)


class ProxmoxError(AppError):
    def __init__(self, message: str = "Proxmox operation failed"):
        super().__init__(message, 502)
