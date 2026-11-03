"""Platform-wide Standardized Exception Hierarchy."""


class LogPlatformException(Exception):
    """Base exception for all errors originating within the platform."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(LogPlatformException):
    """Raised when environment or settings configuration is invalid."""


class IngestionError(LogPlatformException):
    """Raised during log reading, validation, or ingestion pipeline failures."""


class InvalidLogFormatError(IngestionError):
    """Raised when an unparseable or unrecognized log format is encountered."""


class ParsingError(LogPlatformException):
    """Raised during Drain3 template mining or log parsing operations."""


class TemplateNotFoundError(ParsingError):
    """Raised when a referenced template ID does not exist in the catalog."""


class FeatureExtractionError(LogPlatformException):
    """Raised when building sliding windows or extracting feature vectors fails."""


class ModelError(LogPlatformException):
    """Base exception for machine learning model failures."""


class ModelNotTrainedError(ModelError):
    """Raised when inference is attempted on an uninitialized/untrained model."""


class ModelNotFoundError(ModelError):
    """Raised when a requested model artifact or version is not found."""


class ModelInferenceError(ModelError):
    """Raised when inference execution encounters mathematical or tensor errors."""


class AlertError(LogPlatformException):
    """Raised during alert generation, deduplication, or notification routing."""


class IncidentCorrelationError(LogPlatformException):
    """Raised during anomaly clustering or incident generation."""


class DatabaseError(LogPlatformException):
    """Raised during database session, transaction, or ORM operations."""
