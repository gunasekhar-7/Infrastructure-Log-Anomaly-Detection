"""Unit tests for Alert Management and Incident Correlation."""

from datetime import datetime, timezone
import pytest

from src.intelligence import (
    Alert,
    AlertManager,
    AlertStatus,
    AnomalyCategory,
    AnomalySeverity,
    DetectedAnomaly,
    Incident,
    IncidentCorrelator,
    IncidentStatus,
    LogEvidenceItem,
)


@pytest.fixture
def sample_anomaly() -> DetectedAnomaly:
    """Create sample high-severity DetectedAnomaly."""
    return DetectedAnomaly(
        host="node-01",
        service="payment-service",
        anomaly_score=0.88,
        severity=AnomalySeverity.HIGH,
        anomaly_category=AnomalyCategory.SEQUENCE_DEVIATION,
        algorithm="DEEPLOG_LSTM",
        explanation="Unexpected sequence transition E1 -> E99",
        related_templates=["E1", "E99"],
        supporting_evidence=[
            LogEvidenceItem(
                event_id="ev_01",
                timestamp=datetime.now(timezone.utc),
                template_id="E99",
                raw_message="Critical transaction aborted",
                severity="ERROR",
                is_trigger=True,
            )
        ],
    )


def test_alert_generation_and_cooldown(sample_anomaly: DetectedAnomaly) -> None:
    """Verify alert generation, cooldown deduplication, and repeat count tracking."""
    manager = AlertManager(cooldown_seconds=60, min_severity=AnomalySeverity.MEDIUM)

    # 1. Initial anomaly creates a new alert
    alert1 = manager.process_anomaly(sample_anomaly)
    assert alert1 is not None
    assert alert1.status == AlertStatus.NEW
    assert alert1.severity == AnomalySeverity.HIGH
    assert alert1.repeat_count == 1
    assert alert1.host == "node-01"

    # 2. Duplicate anomaly arriving immediately is suppressed and repeat count increments
    alert2 = manager.process_anomaly(sample_anomaly)
    assert alert2 is not None
    assert alert2.alert_id == alert1.alert_id
    assert alert2.repeat_count == 2

    # Verify audit trail captured suppression
    audit = manager.get_audit_trail(alert1.alert_id)
    assert any(e.action == "DUPLICATE_SUPPRESSED" for e in audit)


def test_alert_min_severity_filter() -> None:
    """Verify anomalies below min_severity are ignored."""
    manager = AlertManager(min_severity=AnomalySeverity.HIGH)
    low_anom = DetectedAnomaly(
        host="node-01",
        service="web",
        anomaly_score=0.3,
        severity=AnomalySeverity.LOW,
        anomaly_category=AnomalyCategory.FREQUENCY_SPIKE,
        algorithm="STATISTICAL",
        explanation="Minor event fluctuation",
    )

    alert = manager.process_anomaly(low_anom)
    assert alert is None
    assert len(manager.get_all_alerts()) == 0


def test_alert_lifecycle_transitions(sample_anomaly: DetectedAnomaly) -> None:
    """Verify full alert operational lifecycle transitions and auditing."""
    manager = AlertManager()
    alert = manager.process_anomaly(sample_anomaly)
    assert alert is not None
    alert_id = alert.alert_id

    # Acknowledge
    ack_alert = manager.acknowledge_alert(alert_id, actor="alice_sre")
    assert ack_alert.status == AlertStatus.ACKNOWLEDGED
    assert ack_alert.acknowledged_at is not None

    # Investigate
    inv_alert = manager.investigate_alert(alert_id, actor="alice_sre")
    assert inv_alert.status == AlertStatus.INVESTIGATING

    # Resolve
    res_alert = manager.resolve_alert(alert_id, actor="alice_sre", note="Restarted container")
    assert res_alert.status == AlertStatus.RESOLVED
    assert res_alert.resolved_by == "alice_sre"
    assert res_alert.resolution_note == "Restarted container"

    # Check audit log entries
    audit = manager.get_audit_trail(alert_id)
    assert len(audit) >= 4  # CREATED, ACKNOWLEDGED, INVESTIGATING, RESOLVED


def test_incident_correlation_single_service(sample_anomaly: DetectedAnomaly) -> None:
    """Verify grouping related alerts into a unified incident."""
    correlator = IncidentCorrelator(correlation_window_seconds=300)

    alert1 = Alert(
        anomaly_id=sample_anomaly.anomaly_id,
        title="High anomaly alert 1",
        severity=AnomalySeverity.HIGH,
        host="node-01",
        service="payment-service",
        deduplication_key="key1",
    )

    inc1 = correlator.correlate_alert(alert1, sample_anomaly)
    assert inc1.status == IncidentStatus.OPEN
    assert inc1.primary_service == "payment-service"
    assert inc1.affected_hosts == ["node-01"]
    assert len(inc1.alert_ids) == 1

    # Second alert on same service, different host (cascading failure)
    anomaly2 = DetectedAnomaly(
        host="node-02",
        service="payment-service",
        anomaly_score=0.95,
        severity=AnomalySeverity.CRITICAL,
        anomaly_category=AnomalyCategory.SEQUENCE_DEVIATION,
        algorithm="DEEPLOG_LSTM",
        explanation="Crash loop on node 2",
        related_templates=["E99"],
    )
    alert2 = Alert(
        anomaly_id=anomaly2.anomaly_id,
        title="Critical alert 2",
        severity=AnomalySeverity.CRITICAL,
        host="node-02",
        service="payment-service",
        deduplication_key="key2",
    )

    inc2 = correlator.correlate_alert(alert2, anomaly2)
    assert inc2.incident_id == inc1.incident_id
    assert len(inc2.alert_ids) == 2
    assert "node-01" in inc2.affected_hosts
    assert "node-02" in inc2.affected_hosts
    # Severity should escalate to CRITICAL
    assert inc2.severity == AnomalySeverity.CRITICAL


def test_incident_correlation_separation_different_services(sample_anomaly: DetectedAnomaly) -> None:
    """Verify distinct services are NOT merged into the same incident."""
    correlator = IncidentCorrelator(correlation_window_seconds=300)

    alert1 = Alert(
        anomaly_id="anom_1",
        title="Payment Alert",
        severity=AnomalySeverity.HIGH,
        host="node-01",
        service="payment-service",
        deduplication_key="k1",
    )
    inc1 = correlator.correlate_alert(alert1, sample_anomaly)

    # Anomaly on a completely different service (auth-service)
    anomaly_auth = DetectedAnomaly(
        host="node-01",
        service="auth-service",
        anomaly_score=0.8,
        severity=AnomalySeverity.HIGH,
        anomaly_category=AnomalyCategory.FREQUENCY_SPIKE,
        algorithm="ISOLATION_FOREST",
        explanation="Auth burst",
        related_templates=["E55"],
    )
    alert_auth = Alert(
        anomaly_id="anom_auth",
        title="Auth Alert",
        severity=AnomalySeverity.HIGH,
        host="node-01",
        service="auth-service",
        deduplication_key="k2",
    )

    inc2 = correlator.correlate_alert(alert_auth, anomaly_auth)
    assert inc1.incident_id != inc2.incident_id
    assert inc1.primary_service == "payment-service"
    assert inc2.primary_service == "auth-service"

