"""Data models for Drain3 Log Parsing and Template Mining."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from src.ingestion.models import LogEvent, LogSeverity, ParsingStatus


class LogTemplate(BaseModel):
    """Metadata for a unique mined log template."""

    template_id: str = Field(..., description="Unique canonical template identifier (e.g. E1, E2)")
    template_pattern: str = Field(..., description="Normalized template pattern with <*> wildcards")
    occurrence_count: int = Field(default=1, description="Total number of log lines matching this template")
    first_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sample_parameters: list[str] = Field(default_factory=list, description="Recent parameter sample")


class ParsedLogEvent(BaseModel):
    """Structured log event augmented with Drain3 mined template and extracted parameters."""

    event_id: str
    timestamp: datetime
    host: str
    service: str
    component: str
    severity: LogSeverity
    message: str
    raw_log: str
    source_id: str
    template_id: str = Field(..., description="Canonical template ID (e.g. E1)")
    template_text: str = Field(..., description="Mined template with placeholders")
    parameters: list[str] = Field(default_factory=list, description="Dynamic extracted parameters")
    is_unseen_template: bool = Field(default=False, description="True if this log spawned a new template cluster")
    parsing_status: ParsingStatus = Field(default=ParsingStatus.VALID)
    attributes: dict[str, Any] = Field(default_factory=dict)
    parsing_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_log_event(
        cls,
        event: LogEvent,
        template_id: str,
        template_text: str,
        parameters: list[str] | None = None,
        is_unseen_template: bool = False,
    ) -> "ParsedLogEvent":
        """Factory constructor creating ParsedLogEvent from an ingested LogEvent."""
        return cls(
            event_id=event.event_id,
            timestamp=event.timestamp,
            host=event.host,
            service=event.service,
            component=event.component,
            severity=event.severity,
            message=event.message,
            raw_log=event.raw_log,
            source_id=event.source_id,
            template_id=template_id,
            template_text=template_text,
            parameters=parameters or [],
            is_unseen_template=is_unseen_template,
            parsing_status=event.parsing_status,
            attributes=event.attributes,
            parsing_timestamp=datetime.now(timezone.utc),
        )

