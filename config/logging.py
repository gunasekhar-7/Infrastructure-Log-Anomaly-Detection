"""Structured Logging Setup for Log Anomaly Detection Platform."""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects with ISO 8601 timestamps."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }

        # Include custom correlation attributes if present
        if hasattr(record, "correlation_id"):
            log_payload["correlation_id"] = record.correlation_id
        if hasattr(record, "job_id"):
            log_payload["job_id"] = record.job_id
        if hasattr(record, "source_id"):
            log_payload["source_id"] = record.source_id

        # Include exception traceback if an exception occurred
        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_payload)


class ColoredConsoleFormatter(logging.Formatter):
    """Human-friendly colored console formatter for local development."""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = super().format(record)
        return f"{color}[{timestamp}] [{record.levelname:<8}]{self.RESET} {record.name}: {message}"


def setup_logging(
    level: str = "INFO",
    json_format: bool = False
) -> None:
    """Initialize root and application loggers."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            ColoredConsoleFormatter("%(message)s")
        )

    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Retrieve named logger."""
    return logging.getLogger(name)

