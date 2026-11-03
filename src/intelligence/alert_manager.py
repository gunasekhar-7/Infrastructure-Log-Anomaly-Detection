"""Alert Management, Deduplication, Cooldown, and Lifecycle Routing."""

from datetime import datetime, timezone
import hashlib
from threading import RLock
from typing import Any

from config.logging import get_logger
from src.intelligence.alert_models import Alert, AlertStatus, AuditLogEntry
from src.intelligence.models import AnomalySeverity, DetectedAnomaly
from src.intelligence.notifier import NotificationDispatcher

logger = get_logger("alert_manager")

SEVERITY_ORDER = {
    AnomalySeverity.INFO: 0,
    AnomalySeverity.LOW: 1,
    AnomalySeverity.MEDIUM: 2,
    AnomalySeverity.HIGH: 3,
    AnomalySeverity.CRITICAL: 4,
}


class AlertManager:
    """Manages alert generation, sliding-window deduplication, and lifecycle auditing."""

    def __init__(
        self,
        cooldown_seconds: int = 300,
        min_severity: AnomalySeverity = AnomalySeverity.MEDIUM,
        notifier: NotificationDispatcher | None = None,
    ) -> None:
        self.cooldown_seconds = cooldown_seconds
        self.min_severity = min_severity
        self.notifier = notifier or NotificationDispatcher()

        self._alerts: dict[str, Alert] = {}
        self._active_dedup_keys: dict[str, str] = {}  # dedup_key -> alert_id
        self._audit_log: list[AuditLogEntry] = []
        self._lock = RLock()

    def _generate_dedup_key(self, anomaly: DetectedAnomaly) -> str:
        """Create a deterministic signature for deduplicating identical anomaly sequences."""
        primary_tmpl = anomaly.related_templates[0] if anomaly.related_templates else "NONE"
        raw_key = f"{anomaly.host}|{anomaly.service}|{anomaly.anomaly_category.value}|{primary_tmpl}"
        return hashlib.md5(raw_key.encode("utf-8")).hexdigest()

    def process_anomaly(self, anomaly: DetectedAnomaly) -> Alert | None:
        """Evaluate a detected anomaly and generate an alert or increment duplicate count."""
        # Check severity threshold filter
        if SEVERITY_ORDER[anomaly.severity] < SEVERITY_ORDER[self.min_severity]:
            logger.debug(
                "Suppressed alert for anomaly %s: severity %s below minimum %s",
                anomaly.anomaly_id,
                anomaly.severity.value,
                self.min_severity.value,
            )
            return None

        now = datetime.now(timezone.utc)
        dedup_key = self._generate_dedup_key(anomaly)

        with self._lock:
            # Check for existing active alert within cooldown window
            existing_alert_id = self._active_dedup_keys.get(dedup_key)
            if existing_alert_id and existing_alert_id in self._alerts:
                existing_alert = self._alerts[existing_alert_id]
                time_since_trigger = (now - existing_alert.triggered_at).total_seconds()

                if time_since_trigger < self.cooldown_seconds:
                    # Suppress alert storm: increment repeat count on existing alert
                    existing_alert.repeat_count += 1
                    existing_alert.last_repeated_at = now
                    # Escalate severity if incoming anomaly is higher
                    if SEVERITY_ORDER[anomaly.severity] > SEVERITY_ORDER[existing_alert.severity]:
                        existing_alert.severity = anomaly.severity

                    self._log_audit(
                        entity_type="ALERT",
                        entity_id=existing_alert.alert_id,
                        action="DUPLICATE_SUPPRESSED",
                        details={
                            "repeat_count": existing_alert.repeat_count,
                            "incoming_anomaly_id": anomaly.anomaly_id,
                        },
                    )
                    logger.info(
                        "Alert cooldown active: suppressed duplicate alert for %s (repeat_count=%d)",
                        existing_alert.alert_id,
                        existing_alert.repeat_count,
                    )
                    return existing_alert

            # Create brand new alert
            title = f"[{anomaly.severity.value}] {anomaly.anomaly_category.value} in {anomaly.service} on {anomaly.host}"
            new_alert = Alert(
                anomaly_id=anomaly.anomaly_id,
                title=title,
                severity=anomaly.severity,
                status=AlertStatus.NEW,
                host=anomaly.host,
                service=anomaly.service,
                triggered_at=now,
                deduplication_key=dedup_key,
                repeat_count=1,
                context_metadata={
                    "anomaly_score": anomaly.anomaly_score,
                    "algorithm": anomaly.algorithm,
                    "explanation": anomaly.explanation,
                },
            )

            self._alerts[new_alert.alert_id] = new_alert
            self._active_dedup_keys[dedup_key] = new_alert.alert_id

            self._log_audit(
                entity_type="ALERT",
                entity_id=new_alert.alert_id,
                action="CREATED",
                details={"severity": new_alert.severity.value, "title": new_alert.title},
            )

        logger.info("Created new alert %s: %s", new_alert.alert_id, new_alert.title)
        return new_alert

    def acknowledge_alert(self, alert_id: str, actor: str = "on_call_sre") -> Alert:
        """Mark alert as acknowledged by an operator."""
        with self._lock:
            alert = self._get_or_raise(alert_id)
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_at = datetime.now(timezone.utc)
            self._log_audit("ALERT", alert_id, "STATUS_CHANGE", actor, {"new_status": "ACKNOWLEDGED"})
            return alert

    def investigate_alert(self, alert_id: str, actor: str = "on_call_sre") -> Alert:
        """Mark alert as actively under investigation."""
        with self._lock:
            alert = self._get_or_raise(alert_id)
            alert.status = AlertStatus.INVESTIGATING
            self._log_audit("ALERT", alert_id, "STATUS_CHANGE", actor, {"new_status": "INVESTIGATING"})
            return alert

    def resolve_alert(
        self,
        alert_id: str,
        actor: str = "on_call_sre",
        note: str = "Issue mitigated",
    ) -> Alert:
        """Resolve alert and free deduplication cooldown key."""
        with self._lock:
            alert = self._get_or_raise(alert_id)
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = datetime.now(timezone.utc)
            alert.resolved_by = actor
            alert.resolution_note = note

            # Remove from active deduplication keys so future occurrences trigger fresh alerts
            if alert.deduplication_key in self._active_dedup_keys:
                del self._active_dedup_keys[alert.deduplication_key]

            self._log_audit(
                "ALERT",
                alert_id,
                "STATUS_CHANGE",
                actor,
                {"new_status": "RESOLVED", "note": note},
            )
            return alert

    def mark_false_positive(
        self,
        alert_id: str,
        actor: str = "on_call_sre",
        reason: str = "Normal scheduled maintenance",
    ) -> Alert:
        """Reclassify alert as false positive."""
        with self._lock:
            alert = self._get_or_raise(alert_id)
            alert.status = AlertStatus.FALSE_POSITIVE
            alert.resolved_at = datetime.now(timezone.utc)
            alert.resolved_by = actor
            alert.resolution_note = f"False Positive: {reason}"

            if alert.deduplication_key in self._active_dedup_keys:
                del self._active_dedup_keys[alert.deduplication_key]

            self._log_audit(
                "ALERT",
                alert_id,
                "RECLASSIFIED",
                actor,
                {"new_status": "FALSE_POSITIVE", "reason": reason},
            )
            return alert

    def get_alert(self, alert_id: str) -> Alert | None:
        """Get alert by ID."""
        with self._lock:
            return self._alerts.get(alert_id)

    def get_all_alerts(self, status: AlertStatus | None = None) -> list[Alert]:
        """List alerts with optional status filtering."""
        with self._lock:
            alerts = list(self._alerts.values())
            if status:
                return [a for a in alerts if a.status == status]
            return alerts

    def get_audit_trail(self, entity_id: str | None = None) -> list[AuditLogEntry]:
        """Retrieve audit log history."""
        with self._lock:
            if entity_id:
                return [e for e in self._audit_log if e.entity_id == entity_id]
            return list(self._audit_log)

    def _get_or_raise(self, alert_id: str) -> Alert:
        """Helper to get alert or raise KeyError."""
        if alert_id not in self._alerts:
            raise KeyError(f"Alert ID '{alert_id}' not found.")
        return self._alerts[alert_id]

    def _log_audit(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        actor: str = "SYSTEM",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Append immutable audit log entry."""
        entry = AuditLogEntry(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor=actor,
            details=details or {},
        )
        self._audit_log.append(entry)

