"""Data models for Alert Management, Incident Correlation, and Auditing."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, Field

from src.intelligence.models import AnomalySeverity, LogEvidenceItem


class AlertStatus(str, Enum):
    """Lifecycle statuses for operational alerts."""
    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


class IncidentStatus(str, Enum):
    """Lifecycle statuses for correlated incidents."""
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    MITIGATED = "MITIGATED"
    RESOLVED = "RESOLVED"


class Alert(BaseModel):
    """Operational alert generated from an assessed infrastructure anomaly."""

    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    anomaly_id: str
    incident_id: str | None = None
    title: str
    severity: AnomalySeverity
    status: AlertStatus = AlertStatus.NEW
    host: str
    service: str
    triggered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    resolution_note: str | None = None
    deduplication_key: str
    repeat_count: int = 1
    last_repeated_at: datetime | None = None
    context_metadata: dict[str, Any] = Field(default_factory=dict)


class Incident(BaseModel):
    """Correlated cluster of related alerts representing a potential infrastructure event."""

    incident_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    severity: AnomalySeverity
    status: IncidentStatus = IncidentStatus.OPEN
    primary_service: str
    affected_hosts: list[str] = Field(default_factory=list)
    related_templates: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    alert_ids: list[str] = Field(default_factory=list)
    anomaly_ids: list[str] = Field(default_factory=list)
    consolidated_evidence: list[LogEvidenceItem] = Field(default_factory=list)
    summary: str = ""


class AuditLogEntry(BaseModel):
    """Immutable audit trail entry for alert and incident state modifications."""

    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    entity_type: str  # "ALERT" or "INCIDENT"
    entity_id: str
    action: str       # "CREATED", "STATUS_CHANGE", "ASSIGNED", "NOTE_ADDED", "CORRELATED"
    actor: str = "SYSTEM"
    details: dict[str, Any] = Field(default_factory=dict)
