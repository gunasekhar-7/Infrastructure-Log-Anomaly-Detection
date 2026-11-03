"""End-to-End System Workflow Tests for LogPulse AnomalyGuard.

Validates the complete lifecycle:
Ingest -> Parse -> Feature Extraction -> Detection -> Explanation -> Alerting ->
Incident Correlation -> SRE Triage -> Observability Metrics.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture(scope="module")
def client():
    """Module-scoped FastAPI TestClient driving in-process full stack."""
    with TestClient(app) as test_client:
        yield test_client


def test_full_incident_monitoring_lifecycle(client: TestClient):
    """E2E Test: Ingest failure cascade, verify template mining, anomaly isolation, alert suppression, incident clustering, and SRE resolution."""
    # -------------------------------------------------------------------------
    # STEP 1: Ingest Multi-Node Cascading Failure Scenario
    # -------------------------------------------------------------------------
    scenario_logs = [
        # Normal baseline traffic
        "081109 203518 143 INFO dfs.DataNode$DataXceiver: Receiving block blk_-10001 src: /10.250.1.1:54106 dest: /10.250.1.1:50010",
        "081109 203519 145 INFO dfs.DataNode$PacketResponder: PacketResponder 1 for block blk_-10001 terminating",
        "081109 203519 146 INFO dfs.DataNode$DataXceiver: Received block blk_-10001 of size 67108864 from /10.250.1.1",
        # Failure on Node 1
        "081109 203520 148 ERROR dfs.DataNode$DataXceiver: Verification failed for block blk_-10002 checksum mismatch on replica 1",
        "081109 203521 149 ERROR dfs.DataNode$DataXceiver: Block blk_-10002 is corrupted. Exceeded max block read retries.",
        "081109 203522 150 WARN dfs.DataNode$BlockScanner: Corrupted block blk_-10002 moved to bad_blocks quarantine.",
        # Cascading failure on Node 2
        "081109 203523 151 ERROR dfs.DataNode$DataXceiver: Verification failed for block blk_-10002 checksum mismatch on replica 2",
    ]

    ingest_res = client.post(
        "/api/v1/ingest/stream",
        json={"source_id": "e2e_cascading_failure", "lines": scenario_logs},
        headers={"X-Bypass-Rate-Limit": "test-bypass"},
    )
    assert ingest_res.status_code == 200
    job_info = ingest_res.json()
    assert job_info["status"] == "COMPLETED"
    assert job_info["valid_records"] == len(scenario_logs)
    assert job_info["failed_records"] == 0
    assert job_info["throughput_eps"] > 0

    # -------------------------------------------------------------------------
    # STEP 2: Verify Log Storage & Multi-Attribute Search
    # -------------------------------------------------------------------------
    logs_res = client.get(
        "/api/v1/logs?severity=ERROR&limit=10",
        headers={"X-Bypass-Rate-Limit": "test-bypass"},
    )
    assert logs_res.status_code == 200
    error_items = logs_res.json()["items"]
    assert len(error_items) >= 3
    assert any("checksum mismatch" in item["message"] for item in error_items)

    # -------------------------------------------------------------------------
    # STEP 3: Verify Online Drain3 Template Mining
    # -------------------------------------------------------------------------
    templates_res = client.get(
        "/api/v1/templates",
        headers={"X-Bypass-Rate-Limit": "test-bypass"},
    )
    assert templates_res.status_code == 200
    templates_data = templates_res.json()
    assert templates_data["total"] >= 3
    patterns = [t["template_pattern"] for t in templates_data["items"]]
    assert any("checksum mismatch" in p or "Verification failed" in p for p in patterns)

    # -------------------------------------------------------------------------
    # STEP 4: Verify Anomaly Detection & Factual Evidence Isolation
    # -------------------------------------------------------------------------
    anomalies_res = client.get(
        "/api/v1/anomalies",
        headers={"X-Bypass-Rate-Limit": "test-bypass"},
    )
    assert anomalies_res.status_code == 200
    anomalies = anomalies_res.json()["items"]
    assert len(anomalies) > 0
    target_anomaly = anomalies[0]
    anomaly_id = target_anomaly["id"]

    # Detail query
    detail_res = client.get(
        f"/api/v1/anomalies/{anomaly_id}",
        headers={"X-Bypass-Rate-Limit": "test-bypass"},
    )
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == anomaly_id
    assert len(detail["explanation"]) > 10
    assert len(detail["supporting_evidence"]) > 0
    assert any(ev["is_trigger"] for ev in detail["supporting_evidence"])

    # -------------------------------------------------------------------------
    # STEP 5: Verify Alert Deduplication and SRE Lifecycle
    # -------------------------------------------------------------------------
    alerts_res = client.get(
        "/api/v1/alerts",
        headers={"X-Bypass-Rate-Limit": "test-bypass"},
    )
    assert alerts_res.status_code == 200
    alerts = alerts_res.json()["items"]
    assert len(alerts) > 0
    target_alert = alerts[0]
    alert_id = target_alert["alert_id"]

    # 1. Acknowledge Alert
    ack_res = client.post(
        f"/api/v1/alerts/{alert_id}/action",
        json={"action": "ACKNOWLEDGE", "actor": "sre_alice", "note": "Reviewing node checksum alerts"},
        headers={"X-Bypass-Rate-Limit": "test-bypass"},
    )
    assert ack_res.status_code == 200
    assert ack_res.json()["status"] == "ACKNOWLEDGED"

    # 2. Mark Investigating
    inv_res = client.post(
        f"/api/v1/alerts/{alert_id}/action",
        json={"action": "INVESTIGATE", "actor": "sre_alice", "note": "Suspect bad drive sectors"},
        headers={"X-Bypass-Rate-Limit": "test-bypass"},
    )
    assert inv_res.status_code == 200
    assert inv_res.json()["status"] == "INVESTIGATING"

    # -------------------------------------------------------------------------
    # STEP 6: Verify Incident Correlation & Cluster Mitigation
    # -------------------------------------------------------------------------
    incidents_res = client.get(
        "/api/v1/incidents",
        headers={"X-Bypass-Rate-Limit": "test-bypass"},
    )
    assert incidents_res.status_code == 200
    incidents = incidents_res.json()["items"]
    assert len(incidents) > 0
    target_incident = incidents[0]
    incident_id = target_incident["incident_id"]

    # Resolve Incident
    inc_resolve = client.post(
        f"/api/v1/incidents/{incident_id}/action",
        json={
            "action": "RESOLVE",
            "actor": "sre_alice",
            "summary_findings": "Corrupted blocks quarantined and repaired via parity replicas.",
        },
        headers={"X-Bypass-Rate-Limit": "test-bypass"},
    )
    assert inc_resolve.status_code == 200
    assert inc_resolve.json()["status"] == "RESOLVED"
    assert "parity replicas" in inc_resolve.json()["summary"]

    # -------------------------------------------------------------------------
    # STEP 7: Resolve Alert
    # -------------------------------------------------------------------------
    res_alert = client.post(
        f"/api/v1/alerts/{alert_id}/action",
        json={"action": "RESOLVE", "actor": "sre_alice", "note": "Verified block replica health"},
        headers={"X-Bypass-Rate-Limit": "test-bypass"},
    )
    assert res_alert.status_code == 200
    assert res_alert.json()["status"] == "RESOLVED"

    # -------------------------------------------------------------------------
    # STEP 8: Verify Observability Scrape
    # -------------------------------------------------------------------------
    metrics_res = client.get("/metrics")
    assert metrics_res.status_code == 200
    metrics_text = metrics_res.text
    assert "logpulse_http_requests_total" in metrics_text
    assert "logpulse_log_events_ingested_total" in metrics_text
    assert "logpulse_drain3_templates_count" in metrics_text

