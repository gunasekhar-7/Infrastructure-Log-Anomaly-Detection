"""Data models and schemas for the Log Ingestion Engine."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, Field


class LogSeverity(str, Enum):
    """Normalized log severity levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"


class ParsingStatus(str, Enum):
    """Status of raw log normalization and format parsing."""
    VALID = "VALID"
    FALLBACK = "FALLBACK"
    INVALID_FORMAT = "INVALID_FORMAT"


class LogEvent(BaseModel):
    """Standardized internal representation of an ingested log record."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Event timestamp normalized to UTC"
    )
    host: str = Field(default="localhost", description="Originating host or node name")
    service: str = Field(default="default", description="Originating service or application")
    component: str = Field(default="system", description="Subsystem, logger name, or component")
    severity: LogSeverity = Field(default=LogSeverity.INFO, description="Normalized severity level")
    message: str = Field(..., description="Normalized message body for template mining")
    raw_log: str = Field(..., description="Original, unparsed raw log line")
    source_id: str = Field(default="stream", description="Source file name or stream identifier")
    ingestion_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    parsing_status: ParsingStatus = Field(default=ParsingStatus.VALID)
    is_duplicate: bool = Field(default=False, description="Flag indicating if line was identified as duplicate")
    attributes: dict[str, Any] = Field(default_factory=dict, description="Extracted contextual metadata")


class IngestionStats(BaseModel):
    """Performance and telemetry metrics for an ingestion run."""

    source_id: str
    total_records: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    duplicate_records: int = 0
    bytes_processed: int = 0
    duration_ms: float = 0.0
    throughput_eps: float = Field(default=0.0, description="Events processed per second")


class DeadLetterRecord(BaseModel):
    """Container for unparseable or rejected log records to prevent silent data loss."""

    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_content: str
    failure_reason: str
    source_id: str

