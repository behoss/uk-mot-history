"""Exceptions raised by the client."""

from __future__ import annotations


class MotHistoryError(Exception):
    """Base class for every error this package raises."""

    def __init__(self, message: str, *, status: int | None = None, error_code: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.error_code = error_code


class ConfigurationError(MotHistoryError):
    """Credentials are missing or incomplete."""


class AuthenticationError(MotHistoryError):
    """The token endpoint or the API refused the credentials (401/403)."""


class VehicleNotFound(MotHistoryError):
    """No vehicle matches the registration or VIN (404)."""


class InvalidRequest(MotHistoryError):
    """The API rejected the request as malformed (400), usually an invalid registration or VIN."""


class RateLimited(MotHistoryError):
    """Still throttled (429) after every retry. Limits: 15 requests a second, 500,000 a day."""


class UpstreamError(MotHistoryError):
    """The API kept failing (5xx or network errors) after every retry."""
