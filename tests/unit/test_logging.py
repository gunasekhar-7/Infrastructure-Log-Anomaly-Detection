"""Unit tests for structured and colored logging."""

import json
import logging

from config.logging import JSONFormatter, get_logger, setup_logging


def test_json_formatter() -> None:
    """Verify JSONFormatter produces valid JSON with required fields."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.ERROR,
        pathname=__file__,
        lineno=42,
        msg="Test error event: %s",
        args=("disk_full",),
        exc_info=None
    )
    record.correlation_id = "req-12345"

    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["level"] == "ERROR"
    assert parsed["logger"] == "test_logger"
    assert parsed["message"] == "Test error event: disk_full"
    assert parsed["correlation_id"] == "req-12345"
    assert "timestamp" in parsed


def test_setup_logging() -> None:
    """Verify setup_logging configures root logger without error."""
    setup_logging(level="DEBUG", json_format=True)
    logger = get_logger("app_test")
    assert logger.isEnabledFor(logging.DEBUG)

    # Revert to console for default runs
    setup_logging(level="INFO", json_format=False)

