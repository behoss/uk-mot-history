"""Python client for the UK DVSA MOT History API: MOT tests, mileage and defects by registration or VIN."""

from .client import MotHistoryClient, normalise_registration
from .errors import (
    AuthenticationError,
    ConfigurationError,
    InvalidRequest,
    MotHistoryError,
    RateLimited,
    UpstreamError,
    VehicleNotFound,
)
from .mileage import MileageAnomaly, MileageReading, average_annual_miles, find_mileage_anomalies, mileage_readings
from .models import BulkDownload, BulkFile, Defect, MotTest, Vehicle

__version__ = "0.1.0"

__all__ = [
    "AuthenticationError",
    "BulkDownload",
    "BulkFile",
    "ConfigurationError",
    "Defect",
    "InvalidRequest",
    "MileageAnomaly",
    "MileageReading",
    "MotHistoryClient",
    "MotHistoryError",
    "MotTest",
    "RateLimited",
    "UpstreamError",
    "Vehicle",
    "VehicleNotFound",
    "__version__",
    "average_annual_miles",
    "find_mileage_anomalies",
    "mileage_readings",
    "normalise_registration",
]
