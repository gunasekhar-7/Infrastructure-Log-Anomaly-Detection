"""Incident Correlation Engine for Clustering Related Infrastructure Alerts."""

from datetime import datetime, timezone
from threading import RLock
from typing import Any

from config.logging import get_logger
from src.intelligence.alert_models import Alert, Incident, IncidentStatus
from src.intelligence.models import AnomalySeverity, DetectedAnomaly
from src.intelligence.notifier import NotificationDispatcher

logger = get_logger("incident_correlator")

SEVERITY_ORDER = {
    AnomalySeverity.INFO: 0,
    AnomalySeverity.LOW: 1,
    AnomalySeverity.MEDIUM: 2,
    AnomalySeverity.HIGH: 3,
    AnomalySeverity.CRITICAL: 4,
}


class IncidentCorrelator:
    """Spatio-temporal correlation engine grouping related anomalies into unified incidents."""

    def __init__(
        self,
        correlation_window_seconds: int = 600,
        notifier: NotificationDispatcher | None = None,
    ) -> None:
        self.correlation_window_seconds = correlation_window_seconds
        self.notifier = notifier or NotificationDispatcher()

        self._incidents: dict[str, Incident] = {}
        self._lock = RLock()

    def correlate_alert(
        self,
        alert: Alert,
        anomaly: DetectedAnomaly,
    ) -> Incident:
        """Evaluate incoming alert against active incidents, cluster or spawn a new incident."""
        now = datetime.now(timezone.utc)

        with self._lock:
            candidate_incident = self._find_matching_incident(alert, anomaly, now)

            if candidate_incident:
                # Merge into existing incident
                alert.incident_id = candidate_incident.incident_id
                candidate_incident.alert_ids.append(alert.alert_id)
                candidate_incident.anomaly_ids.append(anomaly.anomaly_id)
                candidate_incident.last_seen_at = now

                # Add affected host if new
                if alert.host not in candidate_incident.affected_hosts:
                    candidate_incident.affected_hosts.append(alert.host)

                # Merge related templates
                for t in anomaly.related_templates:
                    if t not in candidate_incident.related_templates:
                        candidate_incident.related_templates.append(t)

                # Escalate incident severity if incoming alert is higher
                if SEVERITY_ORDER[alert.severity] > SEVERITY_ORDER[candidate_incident.severity]:
                    candidate_incident.severity = alert.severity

                # Append new evidence items
                for ev in anomaly.supporting_evidence:
                    candidate_incident.consolidated_evidence.append(ev)

                # Update title and summary
                host_str = f"{len(candidate_incident.affected_hosts)} hosts" if len(candidate_incident.affected_hosts) > 1 else candidate_incident.affected_hosts[0]
                candidate_incident.title = (
                    f"[{candidate_incident.severity.value}] Service Degradation in {candidate_incident.primary_service} "
                    f"({host_str}, {len(candidate_incident.alert_ids)} alerts)"
                )
                logger.info(
                    "Correlated alert %s into existing incident %s (Total alerts: %d)",
                    alert.alert_id,
                    candidate_incident.incident_id,
                    len(candidate_incident.alert_ids),
                )
                return candidate_incident

            # Spawn brand new incident
            new_incident = Incident(
                title=f"[{alert.severity.value}] Incident in {alert.service} on {alert.host}",
                severity=alert.severity,
                status=IncidentStatus.OPEN,
                primary_service=alert.service,
                affected_hosts=[alert.host],
                related_templates=list(anomaly.related_templates),
                started_at=alert.triggered_at,
                last_seen_at=now,
                alert_ids=[alert.alert_id],
                anomaly_ids=[anomaly.anomaly_id],
                consolidated_evidence=list(anomaly.supporting_evidence),
                summary=f"Incident opened following {anomaly.anomaly_category.value} on {alert.host}. {anomaly.explanation}",
            )

            alert.incident_id = new_incident.incident_id
            self._incidents[new_incident.incident_id] = new_incident

        logger.info(
            "Created new incident %s for service '%s' on '%s'",
            new_incident.incident_id,
            new_incident.primary_service,
            alert.host,
        )
        return new_incident

    def _find_matching_incident(
        self,
        alert: Alert,
        anomaly: DetectedAnomaly,
        now: datetime,
    ) -> Incident | None:
        """Scan open incidents to find contextual match based on temporal and service proximity."""
        for inc in self._incidents.values():
            if inc.status in (IncidentStatus.RESOLVED,):
                continue

            # Check temporal window: incident must have had activity within correlation window
            time_since_last_seen = (now - inc.last_seen_at).total_seconds()
            if time_since_last_seen > self.correlation_window_seconds:
                continue

            # Condition 1: Identical service
            if inc.primary_service == alert.service:
                # Same host or overlapping templates
                same_host = alert.host in inc.affected_hosts
                shared_templates = any(t in inc.related_templates for t in anomaly.related_templates)

                if same_host or shared_templates:
                    return inc

                # Condition 2: Multi-host cascading impact across the same service
                if len(inc.affected_hosts) >= 1:
                    return inc

        return None

    def resolve_incident(
        self,
        incident_id: str,
        actor: str = "on_call_sre",
        summary_findings: str = "Root cause addressed and verified normal.",
    ) -> Incident:
        """Resolve an active incident."""
        with self._lock:
            if incident_id not in self._incidents:
                raise KeyError(f"Incident ID '{incident_id}' not found.")

            inc = self._incidents[incident_id]
            inc.status = IncidentStatus.RESOLVED
            inc.summary = f"RESOLVED by {actor}: {summary_findings}"
            logger.info("Resolved incident %s: %s", incident_id, summary_findings)
            return inc

    def get_incident(self, incident_id: str) -> Incident | None:
        """Get incident by ID."""
        with self._lock:
            return self._incidents.get(incident_id)

    def get_all_incidents(self, status: IncidentStatus | None = None) -> list[Incident]:
        """List all incidents with optional status filter."""
        with self._lock:
            incidents = list(self._incidents.values())
            if status:
                return [i for i in incidents if i.status == status]
            return incidents
