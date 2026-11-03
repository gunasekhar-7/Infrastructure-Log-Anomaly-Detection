"""Pydantic Request and Response Schemas for FastAPI REST API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# INGESTION SCHEMAS
# =============================================================================
class IngestStreamRequest(BaseModel):
    """Payload for real-time log line streaming."""
    source_id: str = "stream_source"
    lines: list[str] = Field(..., min_length=1, description="Batch of raw log strings")


class IngestJobResponse(BaseModel):
    """Response returned upon initiation or query of an ingestion job."""
    job_id: str
    source_name: str
    status: str
    total_records: int
    valid_records: int
    failed_records: int
    duration_ms: float
    throughput_eps: float
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None


# =============================================================================
# LOG EVENT SCHEMAS
# =============================================================================
class LogEventResponse(BaseModel):
    """Schema for individual parsed log record in API responses."""
    id: str
    timestamp: datetime
    host: str
    service: str
    component: str
    severity: str
    template_id: str
    message: str
    raw_log: str
    parameters: list[Any] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class PaginatedLogEventsResponse(BaseModel):
    """Paginated list of log events."""
    items: list[LogEventResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# TEMPLATE SCHEMAS
# =============================================================================
class LogTemplateResponse(BaseModel):
    """Schema for mined log template."""
    template_id: str
    template_pattern: str
    occurrence_count: int
    sample_parameters: list[str] = Field(default_factory=list)
    first_seen: datetime
    last_seen: datetime


class PaginatedTemplatesResponse(BaseModel):
    """List of templates."""
    items: list[LogTemplateResponse]
    total: int


# =============================================================================
# ANOMALY SCHEMAS
# =============================================================================
class AnomalyEvidenceResponse(BaseModel):
    """Supporting log evidence item."""
    id: str
    event_id: str
    timestamp: datetime
    template_id: str
    raw_message: str
    severity: str
    is_trigger: bool
    reason: str


class AnomalyResponse(BaseModel):
    """Summary of a detected anomaly."""
    id: str
    timestamp: datetime
    host: str
    service: str
    anomaly_score: float
    severity: str
    category: str
    algorithm: str
    explanation: str
    related_templates: list[str] = Field(default_factory=list)
    investigation_status: str


class AnomalyDetailResponse(AnomalyResponse):
    """Detailed anomaly view with attached evidence."""
    supporting_evidence: list[AnomalyEvidenceResponse] = Field(default_factory=list)
    context_metadata: dict[str, Any] = Field(default_factory=dict)


class PaginatedAnomaliesResponse(BaseModel):
    """Paginated list of anomalies."""
    items: list[AnomalyResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# ALERT SCHEMAS
# =============================================================================
class AlertResponse(BaseModel):
    """Operational alert record."""
    alert_id: str
    anomaly_id: str
    incident_id: str | None = None
    title: str
    severity: str
    status: str
    host: str
    service: str
    triggered_at: datetime
    repeat_count: int
    resolved_by: str | None = None
    resolution_note: str | None = None


class AlertActionRequest(BaseModel):
    """Request payload for updating alert status."""
    action: str = Field(..., description="ACKNOWLEDGE, INVESTIGATE, RESOLVE, or FALSE_POSITIVE")
    actor: str = Field(default="on_call_sre")
    note: str = Field(default="", description="Optional resolution or triage comment")


class PaginatedAlertsResponse(BaseModel):
    """Paginated list of alerts."""
    items: list[AlertResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# INCIDENT SCHEMAS
# =============================================================================
class IncidentResponse(BaseModel):
    """Correlated operational incident."""
    incident_id: str
    title: str
    severity: str
    status: str
    primary_service: str
    affected_hosts: list[str]
    related_templates: list[str]
    started_at: datetime
    last_seen_at: datetime
    alert_count: int
    summary: str


class IncidentActionRequest(BaseModel):
    """Request payload for resolving or updating an incident."""
    action: str = Field(default="RESOLVE", description="INVESTIGATE, MITIGATE, or RESOLVE")
    actor: str = Field(default="on_call_sre")
    summary_findings: str = Field(default="Incident resolved")


class PaginatedIncidentsResponse(BaseModel):
    """Paginated list of incidents."""
    items: list[IncidentResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# HEALTH & METADATA SCHEMAS
# =============================================================================
class HealthResponse(BaseModel):
    """Service health and readiness response."""
    status: str
    version: str
    database: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# MODEL REGISTRY & BENCHMARK SCHEMAS
# =============================================================================
class ModelInfoResponse(BaseModel):
    """Metadata describing a registered anomaly detection model."""
    name: str
    algorithm: str
    category: str
    status: str
    is_active: bool
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class BenchmarkMetricItem(BaseModel):
    """Evaluated performance metrics for a model."""
    model_name: str
    algorithm: str
    threshold: float
    precision: float
    recall: float
    f1_score: float
    roc_auc: float
    training_time_sec: float
    inference_latency_ms: float


class ModelBenchmarkResponse(BaseModel):
    """Collection of benchmark evaluation results."""
    dataset: str
    split_info: str
    metrics: list[BenchmarkMetricItem]
