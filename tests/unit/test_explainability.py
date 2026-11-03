"""Unit tests for Anomaly Classification, Prioritization, and Explainability."""

from datetime import datetime, timezone
import pytest

from src.features.models import SequenceSample, WindowFeatureRecord
from src.ingestion.models import LogSeverity
from src.intelligence import (
    AnomalyAssessor,
    AnomalyCategory,
    AnomalyExplainer,
    AnomalySeverity,
    DetectedAnomaly,
    InvestigationStatus,
    SeverityPrioritizer,
)
from src.parsing.models import ParsedLogEvent


@pytest.fixture
def sample_events() -> list[ParsedLogEvent]:
    """Create sample parsed log events for testing."""
    now = datetime(2026, 11, 3, 14, 0, 0, tzinfo=timezone.utc)
    return [
        ParsedLogEvent(
            event_id="ev_1",
            timestamp=now,
            host="auth-node-1",
            service="auth-service",
            component="Authenticator",
            severity=LogSeverity.INFO,
            message="User login attempt started",
            raw_log="2026-11-03 14:00:00 [INFO] User login attempt started",
            source_id="test.log",
            template_id="E1",
            template_text="User login attempt started",
        ),
        ParsedLogEvent(
            event_id="ev_2",
            timestamp=now,
            host="auth-node-1",
            service="auth-service",
            component="Authenticator",
            severity=LogSeverity.ERROR,
            message="Invalid JWT signature in header",
            raw_log="2026-11-03 14:00:00 [ERROR] Invalid JWT signature in header",
            source_id="test.log",
            template_id="E2",
            template_text="Invalid JWT signature in header",
        ),
    ]


def test_severity_prioritizer_critical() -> None:
    """Verify fatal or severe conditions produce CRITICAL severity."""
    prioritizer = SeverityPrioritizer()
    sev = prioritizer.calculate_severity(
        anomaly_score=0.85,
        fatal_count=1,
        error_rate=0.6,
    )
    assert sev == AnomalySeverity.CRITICAL


def test_severity_prioritizer_levels() -> None:
    """Verify mapping of varied score and contextual signals to appropriate severities."""
    prioritizer = SeverityPrioritizer()

    # High score + error count
    assert prioritizer.calculate_severity(anomaly_score=0.75, error_count=2) == AnomalySeverity.HIGH

    # Moderate score
    assert prioritizer.calculate_severity(anomaly_score=0.55) == AnomalySeverity.MEDIUM

    # Sequence deviation with no errors defaults to MEDIUM
    assert (
        prioritizer.calculate_severity(anomaly_score=0.4, category=AnomalyCategory.SEQUENCE_DEVIATION)
        == AnomalySeverity.MEDIUM
    )

    # Low score
    assert prioritizer.calculate_severity(anomaly_score=0.36) == AnomalySeverity.LOW

    # Negligible score
    assert prioritizer.calculate_severity(anomaly_score=0.15) == AnomalySeverity.INFO


def test_anomaly_explainer_volumetric(sample_events: list[ParsedLogEvent]) -> None:
    """Verify factual volumetric explanation and evidence extraction."""
    explainer = AnomalyExplainer()
    window = WindowFeatureRecord(
        window_id="win_10",
        start_time=datetime(2026, 11, 3, 14, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 11, 3, 14, 1, 0, tzinfo=timezone.utc),
        event_count=10,
        error_count=3,
        warn_count=1,
        info_count=6,
        error_rate=0.3,
        template_entropy=1.5,
        inter_event_time_mean_ms=100.0,
        inter_event_time_std_ms=20.0,
        unique_templates_count=4,
        unique_services_count=1,
        unique_hosts_count=1,
        template_counts={"E1": 6, "E2": 3, "E3": 1},
    )

    explanation, evidence = explainer.explain_volumetric_anomaly(
        window=window,
        events=sample_events,
        anomaly_score=0.78,
        algorithm="ISOLATION_FOREST",
    )

    assert "ISOLATION_FOREST" in explanation
    assert "error rate: 30.0%" in explanation
    assert len(evidence) >= 1
    # Check trigger flag on error event
    assert any(e.is_trigger for e in evidence)


def test_anomaly_explainer_sequential(sample_events: list[ParsedLogEvent]) -> None:
    """Verify factual sequence break explanation with expected top-k candidates."""
    explainer = AnomalyExplainer()
    sample = SequenceSample(
        sample_id="seq_1",
        sequence_templates=["E1", "E2", "E3"],
        sequence_indices=[2, 3, 4],
        next_template="E99",
        next_index=99,
    )
    actual_event = sample_events[1]

    explanation, evidence = explainer.explain_sequential_anomaly(
        sample=sample,
        actual_event=actual_event,
        expected_candidates=["E4", "E5"],
        candidate_prob_sum=0.965,
        anomaly_score=0.88,
    )

    assert "DeepLog" in explanation
    assert "E3" in explanation
    assert "E99" in explanation
    assert "E4, E5" in explanation
    assert "96.5%" in explanation
    assert len(evidence) == 1
    assert evidence[0].is_trigger is True


def test_anomaly_assessor_window(sample_events: list[ParsedLogEvent]) -> None:
    """Verify AnomalyAssessor creates structured DetectedAnomaly record."""
    assessor = AnomalyAssessor()
    window = WindowFeatureRecord(
        window_id="win_01",
        start_time=datetime(2026, 11, 3, 14, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 11, 3, 14, 1, 0, tzinfo=timezone.utc),
        event_count=5,
        error_count=1,
        warn_count=0,
        info_count=4,
        error_rate=0.2,
        template_entropy=0.8,
        inter_event_time_mean_ms=50.0,
        inter_event_time_std_ms=10.0,
        unique_templates_count=2,
        unique_services_count=1,
        unique_hosts_count=1,
        template_counts={"E1": 4, "E2": 1},
    )

    anomaly = assessor.assess_window(
        window=window,
        events=sample_events,
        anomaly_score=0.82,
        algorithm="ISOLATION_FOREST",
    )

    assert isinstance(anomaly, DetectedAnomaly)
    assert anomaly.severity == AnomalySeverity.HIGH
    assert anomaly.anomaly_score == 0.82
    assert anomaly.host == "auth-node-1"
    assert anomaly.service == "auth-service"
    assert anomaly.investigation_status == InvestigationStatus.UNINVESTIGATED
    assert len(anomaly.supporting_evidence) > 0
