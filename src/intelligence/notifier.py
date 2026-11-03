"""Notification and Webhook Dispatcher for Alerts and Incidents."""

from typing import Any
import httpx

from config.logging import get_logger
from src.intelligence.alert_models import Alert, Incident

logger = get_logger("notifier")


class NotificationDispatcher:
    """Dispatches operational alerts and incident notifications to external webhooks."""

    def __init__(self, webhook_url: str | None = None, enabled: bool = True) -> None:
        self.webhook_url = webhook_url
        self.enabled = enabled
        self.sent_notifications: list[dict[str, Any]] = []

    async def send_alert_notification(self, alert: Alert) -> bool:
        """Send formatted alert notification to configured webhook."""
        if not self.enabled:
            return False

        payload = {
            "notification_type": "ALERT",
            "alert_id": alert.alert_id,
            "title": alert.title,
            "severity": alert.severity.value,
            "service": alert.service,
            "host": alert.host,
            "status": alert.status.value,
            "triggered_at": alert.triggered_at.isoformat(),
        }

        self.sent_notifications.append(payload)
        logger.info(
            "DISPATCH ALERT: [%s] %s on %s:%s (AlertID: %s)",
            alert.severity.value,
            alert.title,
            alert.host,
            alert.service,
            alert.alert_id,
        )

        if not self.webhook_url:
            return True

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(self.webhook_url, json=payload)
                return resp.status_code in (200, 201, 202)
        except Exception as exc:
            logger.warning("Failed to dispatch alert webhook to %s: %s", self.webhook_url, exc)
            return False

    async def send_incident_notification(self, incident: Incident) -> bool:
        """Send formatted incident creation or escalation notification."""
        if not self.enabled:
            return False

        payload = {
            "notification_type": "INCIDENT",
            "incident_id": incident.incident_id,
            "title": incident.title,
            "severity": incident.severity.value,
            "status": incident.status.value,
            "primary_service": incident.primary_service,
            "affected_hosts": incident.affected_hosts,
            "alert_count": len(incident.alert_ids),
        }

        self.sent_notifications.append(payload)
        logger.info(
            "DISPATCH INCIDENT: [%s] %s (Service: %s, Alerts: %d, IncidentID: %s)",
            incident.severity.value,
            incident.title,
            incident.primary_service,
            len(incident.alert_ids),
            incident.incident_id,
        )
        return True

