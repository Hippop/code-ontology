from __future__ import annotations

from typing import Any


class PlatformError(Exception):
    """An expected error that can be safely returned by the HTTP boundary."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def invalid(message: str, details: Any | None = None) -> PlatformError:
    return PlatformError(400, "VALIDATION_ERROR", message, details)


def not_found(message: str) -> PlatformError:
    return PlatformError(404, "NOT_FOUND", message)


def conflict(message: str) -> PlatformError:
    return PlatformError(409, "IDEMPOTENCY_CONFLICT", message)
