"""Data models for Anomaly Assessment, Prioritization, and Explainability."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, Field


class AnomalySeverity(str, Enum):
    """Categorical severity levels for prioritized triage."""
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AnomalyCategory(str, Enum):
    """Functional category of anomalous infrastructure behavior."""
    SEQUENCE_DEVIATION = "SEQUENCE_DEVIATION"
    FREQUENCY_SPIKE = "FREQUENCY_SPIKE"
    UNSEEN_TEMPLATE = "UNSEEN_TEMPLATE"
    RECONSTRUCTION_ERROR = "RECONSTRUCTION_ERROR"
    HYBRID = "HYBRID"


class InvestigationStatus(str, Enum):
    """Operational lifecycle status of a detected anomaly."""
    UNINVESTIGATED = "UNINVESTIGATED"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


class LogEvidenceItem(BaseModel):
    """Individual supporting raw log record associated with an anomaly."""

    event_id: str
    timestamp: datetime
    template_id: str
    raw_message: str
    severity: str
    is_trigger: bool = False
    reason: str = ""


class DetectedAnomaly(BaseModel):
    """Rich, actionable anomaly record enriched with severity, explanations, and evidence."""

    anomaly_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    host: str = "localhost"
    service: str = "default"
    anomaly_score: float = Field(..., ge=0.0, le=1.0, description="Normalized score 0.0 to 1.0")
    severity: AnomalySeverity = AnomalySeverity.MEDIUM
    anomaly_category: AnomalyCategory = AnomalyCategory.FREQUENCY_SPIKE
    algorithm: str = "ISOLATION_FOREST"
    explanation: str = Field(..., description="Factual, human-readable detection summary")
    related_templates: list[str] = Field(default_factory=list)
    supporting_evidence: list[LogEvidenceItem] = Field(default_factory=list)
    investigation_status: InvestigationStatus = InvestigationStatus.UNINVESTIGATED
    context_metadata: dict[str, Any] = Field(default_factory=dict)
