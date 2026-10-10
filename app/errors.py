class AppError(Exception):
    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def tenant_not_found() -> AppError:
    return AppError("tenant_not_found", "tenant not found", 404)


def task_not_found() -> AppError:
    return AppError("task_not_found", "task not found", 404)


def tenant_already_exists() -> AppError:
    return AppError("tenant_already_exists", "tenant already exists", 409)


def tenant_update_not_allowed() -> AppError:
    return AppError("tenant_update_not_allowed", "tenant update not allowed", 409)


def tenant_version_conflict() -> AppError:
    return AppError("tenant_version_conflict", "tenant version conflict", 409)


def invalid_request(message: str) -> AppError:
    return AppError("invalid_request", message, 400)
