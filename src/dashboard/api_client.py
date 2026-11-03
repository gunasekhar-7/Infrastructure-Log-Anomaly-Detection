"""API Client for Communication between Streamlit Dashboard and FastAPI Backend."""

import os
from typing import Any
import httpx

from config.logging import get_logger
from config.settings import settings

logger = get_logger("dashboard_api_client")


class DashboardAPIClient:
    """Robust HTTP client with automatic fallback for standalone dashboard execution."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or os.getenv("API_BASE_URL", f"http://localhost:{settings.API_PORT}")
        self.api_prefix = settings.API_PREFIX
        self._test_client = None

    def _get_client(self):
        """Returns standard httpx Client or falls back to in-process FastAPI TestClient."""
        # Check if remote server is reachable
        try:
            with httpx.Client(base_url=self.base_url, timeout=1.0) as client:
                res = client.get("/healthz")
                if res.status_code == 200:
                    return httpx.Client(base_url=self.base_url, timeout=15.0)
        except Exception:
            pass

        # Fallback to in-process FastAPI TestClient for seamless zero-daemon demo
        if self._test_client is None:
            from fastapi.testclient import TestClient
            from src.api.main import app
            self._test_client = TestClient(app)
            logger.info("DashboardAPIClient operating in zero-daemon direct app mode.")
        return self._test_client

    def get_health(self) -> dict[str, Any]:
        """Fetch system health telemetry."""
        client = self._get_client()
        res = client.get("/healthz")
        res.raise_for_status()
        return res.json()

    def get_metrics_raw(self) -> str:
        """Fetch Prometheus raw metrics."""
        client = self._get_client()
        res = client.get("/metrics")
        return res.text if res.status_code == 200 else ""

    def ingest_stream(self, lines: list[str], source_id: str = "dashboard_stream") -> dict[str, Any]:
        """Send batch of log lines for online ingestion."""
        client = self._get_client()
        res = client.post(
            f"{self.api_prefix}/ingest/stream",
            json={"source_id": source_id, "lines": lines},
        )
        res.raise_for_status()
        return res.json()

    def query_logs(
        self,
        service: str | None = None,
        host: str | None = None,
        severity: str | None = None,
        template_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Retrieve paginated log events with filtering."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if service:
            params["service"] = service
        if host:
            params["host"] = host
        if severity:
            params["severity"] = severity
        if template_id:
            params["template_id"] = template_id

        client = self._get_client()
        res = client.get(f"{self.api_prefix}/logs", params=params)
        res.raise_for_status()
        return res.json()

    def get_templates(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """Retrieve mined log template catalog."""
        client = self._get_client()
        res = client.get(f"{self.api_prefix}/templates", params={"limit": limit, "offset": offset})
        res.raise_for_status()
        return res.json()

    def query_anomalies(
        self,
        severity: str | None = None,
        service: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Retrieve detected anomalies."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if severity:
            params["severity"] = severity
        if service:
            params["service"] = service

        client = self._get_client()
        res = client.get(f"{self.api_prefix}/anomalies", params=params)
        res.raise_for_status()
        return res.json()

    def get_anomaly_detail(self, anomaly_id: str) -> dict[str, Any]:
        """Retrieve comprehensive anomaly details with supporting evidence."""
        client = self._get_client()
        res = client.get(f"{self.api_prefix}/anomalies/{anomaly_id}")
        res.raise_for_status()
        return res.json()

    def query_alerts(
        self,
        status: str | None = None,
        severity: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Retrieve operational alerts."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if severity:
            params["severity"] = severity

        client = self._get_client()
        res = client.get(f"{self.api_prefix}/alerts", params=params)
        res.raise_for_status()
        return res.json()

    def post_alert_action(
        self,
        alert_id: str,
        action: str,
        actor: str = "dashboard_user",
        note: str = "",
    ) -> dict[str, Any]:
        """Execute triage action on an alert."""
        client = self._get_client()
        res = client.post(
            f"{self.api_prefix}/alerts/{alert_id}/action",
            json={"action": action, "actor": actor, "note": note},
        )
        res.raise_for_status()
        return res.json()

    def query_incidents(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Retrieve correlated incidents."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status

        client = self._get_client()
        res = client.get(f"{self.api_prefix}/incidents", params=params)
        res.raise_for_status()
        return res.json()

    def post_incident_action(
        self,
        incident_id: str,
        action: str,
        actor: str = "dashboard_user",
        summary_findings: str = "",
    ) -> dict[str, Any]:
        """Execute triage action on an incident."""
        client = self._get_client()
        res = client.post(
            f"{self.api_prefix}/incidents/{incident_id}/action",
            json={"action": action, "actor": actor, "summary_findings": summary_findings},
        )
        res.raise_for_status()
        return res.json()

    def get_models(self) -> list[dict[str, Any]]:
        """Retrieve registered anomaly detector models."""
        client = self._get_client()
        res = client.get(f"{self.api_prefix}/models")
        res.raise_for_status()
        return res.json()

    def get_benchmarks(self) -> dict[str, Any]:
        """Retrieve evaluated model benchmarks."""
        client = self._get_client()
        res = client.get(f"{self.api_prefix}/models/benchmark")
        res.raise_for_status()
        return res.json()

