"""SQLAlchemy 2.0 ORM Entities for Application State and Telemetry."""

from datetime import datetime, timezone
import uuid
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Base declarative class for all database entities."""
    pass


class IngestionJobORM(Base):
    """Tracks asynchronous log file ingestion runs and statistics."""

    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_name: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", index=True)
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    valid_records: Mapped[int] = mapped_column(Integer, default=0)
    failed_records: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    throughput_eps: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LogTemplateORM(Base):
    """Catalog of mined Drain3 log templates."""

    __tablename__ = "log_templates"

    template_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    template_pattern: Mapped[str] = mapped_column(Text)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    sample_parameters_json: Mapped[list | None] = mapped_column(JSON, default=list)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LogEventORM(Base):
    """Parsed structured infrastructure log records."""

    __tablename__ = "log_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("ingestion_jobs.id"), nullable=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    host: Mapped[str] = mapped_column(String(128), index=True)
    service: Mapped[str] = mapped_column(String(128), index=True)
    component: Mapped[str] = mapped_column(String(128))
    severity: Mapped[str] = mapped_column(String(32), index=True)
    template_id: Mapped[str] = mapped_column(String(64), ForeignKey("log_templates.template_id"), index=True)
    message: Mapped[str] = mapped_column(Text)
    raw_log: Mapped[str] = mapped_column(Text)
    parameters_json: Mapped[list | None] = mapped_column(JSON, default=list)
    attributes_json: Mapped[dict | None] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_log_events_time_service", "timestamp", "service"),
    )


class AnomalyORM(Base):
    """Detected operational anomalies."""

    __tablename__ = "anomalies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    host: Mapped[str] = mapped_column(String(128), index=True)
    service: Mapped[str] = mapped_column(String(128), index=True)
    anomaly_score: Mapped[float] = mapped_column(Float, index=True)
    severity: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    algorithm: Mapped[str] = mapped_column(String(64))
    explanation: Mapped[str] = mapped_column(Text)
    related_templates_json: Mapped[list | None] = mapped_column(JSON, default=list)
    investigation_status: Mapped[str] = mapped_column(String(50), default="UNINVESTIGATED", index=True)
    context_metadata_json: Mapped[dict | None] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AnomalyEvidenceORM(Base):
    """Supporting log evidence items associated with an anomaly."""

    __tablename__ = "anomaly_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    anomaly_id: Mapped[str] = mapped_column(String(36), ForeignKey("anomalies.id"), index=True)
    event_id: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    template_id: Mapped[str] = mapped_column(String(64))
    raw_message: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(32))
    is_trigger: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(Text, default="")


class AlertORM(Base):
    """Active and resolved alerts with deduplication counters."""

    __tablename__ = "alerts"

    alert_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    anomaly_id: Mapped[str] = mapped_column(String(36), ForeignKey("anomalies.id"), index=True)
    incident_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(50), default="NEW", index=True)
    host: Mapped[str] = mapped_column(String(128), index=True)
    service: Mapped[str] = mapped_column(String(128), index=True)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    deduplication_key: Mapped[str] = mapped_column(String(64), index=True)
    repeat_count: Mapped[int] = mapped_column(Integer, default=1)
    last_repeated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IncidentORM(Base):
    """Correlated multi-alert operational incidents."""

    __tablename__ = "incidents"

    incident_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(50), default="OPEN", index=True)
    primary_service: Mapped[str] = mapped_column(String(128), index=True)
    affected_hosts_json: Mapped[list | None] = mapped_column(JSON, default=list)
    related_templates_json: Mapped[list | None] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    alert_ids_json: Mapped[list | None] = mapped_column(JSON, default=list)
    anomaly_ids_json: Mapped[list | None] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")


class AuditLogORM(Base):
    """Immutable governance and audit log trail."""

    __tablename__ = "audit_logs"

    entry_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(50), index=True)
    actor: Mapped[str] = mapped_column(String(128), default="SYSTEM")
    details_json: Mapped[dict | None] = mapped_column(JSON, default=dict)

