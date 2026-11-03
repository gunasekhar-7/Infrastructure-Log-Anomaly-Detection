"""Log Ingestion & Normalization Subsystem."""

from src.ingestion.models import (
    LogEvent,
    LogSeverity,
    ParsingStatus,
    IngestionStats,
    DeadLetterRecord,
)
from src.ingestion.engine import LogIngestionEngine
from src.ingestion.detector import LogFormat, detect_line_format, detect_file_format
from src.ingestion.validator import validate_file, sanitize_line
from src.ingestion.normalizer import normalize_severity, normalize_timestamp
from src.ingestion.deduplicator import DuplicateDetector
from src.ingestion.dead_letter import DeadLetterQueue

__all__ = [
    "LogEvent",
    "LogSeverity",
    "ParsingStatus",
    "IngestionStats",
    "DeadLetterRecord",
    "LogIngestionEngine",
    "LogFormat",
    "detect_line_format",
    "detect_file_format",
    "validate_file",
    "sanitize_line",
    "normalize_severity",
    "normalize_timestamp",
    "DuplicateDetector",
    "DeadLetterQueue",
]
