"""Unit tests for platform exceptions."""

import pytest
from src.exceptions import (
    ConfigurationError,
    IngestionError,
    InvalidLogFormatError,
    LogPlatformException,
    ModelInferenceError,
    ModelNotTrainedError,
    ParsingError,
    TemplateNotFoundError,
)


def test_exception_hierarchy() -> None:
    """Verify inheritance structure of custom domain exceptions."""
    assert issubclass(ConfigurationError, LogPlatformException)
    assert issubclass(IngestionError, LogPlatformException)
    assert issubclass(InvalidLogFormatError, IngestionError)
    assert issubclass(ParsingError, LogPlatformException)
    assert issubclass(TemplateNotFoundError, ParsingError)
    assert issubclass(ModelNotTrainedError, LogPlatformException)
    assert issubclass(ModelInferenceError, LogPlatformException)


def test_exception_attributes() -> None:
    """Verify custom exception messages and details dictionaries."""
    exc = InvalidLogFormatError(
        message="Unrecognized log format",
        details={"line": "malformed string", "parser": "drain3"}
    )
    assert str(exc) == "Unrecognized log format"
    assert exc.details["line"] == "malformed string"
    assert exc.details["parser"] == "drain3"
