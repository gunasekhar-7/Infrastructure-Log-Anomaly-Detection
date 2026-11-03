"""Log Ingestion & Normalization Subsystem."""

from src.ingestion.dead_letter import DeadLetterQueue
from src.ingestion.deduplicator import DuplicateDetector
from src.ingestion.detector import LogFormat, detect_file_format, detect_line_format
from src.ingestion.engine import LogIngestionEngine
from src.ingestion.models import (
    DeadLetterRecord,
    IngestionStats,
    LogEvent,
    LogSeverity,
    ParsingStatus,
)
from src.ingestion.normalizer import normalize_severity, normalize_timestamp
from src.ingestion.validator import sanitize_line, validate_file

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
