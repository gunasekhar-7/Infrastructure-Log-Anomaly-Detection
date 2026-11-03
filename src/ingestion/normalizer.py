"""Normalization of Timestamps, Severities, and Log Entities."""

import re
from datetime import datetime, timezone

from src.ingestion.models import LogSeverity

SEVERITY_MAP = {
    "DEBUG": LogSeverity.DEBUG,
    "TRACE": LogSeverity.DEBUG,
    "INFO": LogSeverity.INFO,
    "NOTICE": LogSeverity.INFO,
    "WARN": LogSeverity.WARN,
    "WARNING": LogSeverity.WARN,
    "ERROR": LogSeverity.ERROR,
    "ERR": LogSeverity.ERROR,
    "CRITICAL": LogSeverity.FATAL,
    "FATAL": LogSeverity.FATAL,
    "ALERT": LogSeverity.FATAL,
    "EMERGENCY": LogSeverity.FATAL,
    "FAILURE": LogSeverity.ERROR,
}

# Regex patterns for common timestamp formats
TIMESTAMP_PATTERNS = [
    # ISO 8601: 2026-11-03T10:15:30(.123456)(Z|+00:00)
    (re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$"), "%Y-%m-%d %H:%M:%S"),
    # Standard: 2026-11-03 10:15:30
    (re.compile(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}$"), "%Y-%m-%d %H:%M:%S"),
    # HDFS: 081109 203615 (YYMMDD HHMMSS)
    (re.compile(r"^\d{6}\s+\d{6}$"), "%y%m%d %H%M%S"),
    # BGL timestamp: 2005-06-03-15.42.50.675872
    (re.compile(r"^\d{4}-\d{2}-\d{2}-\d{2}\.\d{2}\.\d{2}(?:\.\d+)?$"), "%Y-%m-%d-%H.%M.%S"),
]


def normalize_severity(raw_severity: str | None) -> LogSeverity:
    """Normalize arbitrary severity strings to standardized LogSeverity enum."""
    if not raw_severity:
        return LogSeverity.INFO
    cleaned = raw_severity.strip().upper()
    return SEVERITY_MAP.get(cleaned, LogSeverity.INFO)


def normalize_timestamp(raw_value: str | int | float | None) -> datetime:
    """Normalize diverse timestamp inputs (epoch, ISO, custom) into UTC datetime."""
    if raw_value is None:
        return datetime.now(timezone.utc)

    # Numeric Epoch timestamp
    if isinstance(raw_value, (int, float)):
        # If timestamp is in milliseconds (> 1e11), convert to seconds
        epoch_sec = raw_value / 1000.0 if raw_value > 1e11 else float(raw_value)
        try:
            return datetime.fromtimestamp(epoch_sec, tz=timezone.utc)
        except (ValueError, OSError):
            return datetime.now(timezone.utc)

    str_val = str(raw_value).strip()

    # Check if string is numeric epoch
    if str_val.isdigit():
        num_epoch = int(str_val)
        epoch_sec = num_epoch / 1000.0 if num_epoch > 1e11 else float(num_epoch)
        try:
            return datetime.fromtimestamp(epoch_sec, tz=timezone.utc)
        except (ValueError, OSError):
            return datetime.now(timezone.utc)

    # Check standard ISO 8601 with fromisoformat
    try:
        dt = datetime.fromisoformat(str_val.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass

    # Try custom timestamp patterns
    for pattern, fmt in TIMESTAMP_PATTERNS:
        if pattern.match(str_val):
            try:
                # Truncate microseconds for BGL if needed
                clean_str = re.sub(r"\.\d+$", "", str_val)
                dt = datetime.strptime(clean_str, fmt).replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue

    # Fallback to current time if unparseable
    return datetime.now(timezone.utc)

