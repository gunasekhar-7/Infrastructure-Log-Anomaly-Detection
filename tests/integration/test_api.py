"""Integration Tests for FastAPI Backend Endpoints and Async Database Layer."""

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture(scope="module")
def client():
    """Module-scoped FastAPI TestClient triggering startup/shutdown lifecycles."""
    with TestClient(app) as test_client:
        yield test_client


# =============================================================================
# OBSERVABILITY & ROOT ENDPOINT TESTS
# =============================================================================
def test_health_check(client: TestClient):
    """Verify /healthz returns UP status and database connectivity."""
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "UP"
    assert "HEALTHY" in data["database"]
    assert "version" in data


def test_prometheus_metrics(client: TestClient):
    """Verify /metrics returns Prometheus format telemetry."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "process_cpu_seconds_total" in response.text or "python_gc_objects_collected_total" in response.text


def test_root_endpoint(client: TestClient):
    """Verify root / returns platform metadata and endpoint map."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "platform" in data
    assert "api_v1" in data
    assert data["api_v1"]["ingest"] == "/api/v1/ingest"


def test_middleware_headers(client: TestClient):
    """Verify custom headers X-Correlation-ID and X-Response-Time-Ms are injected."""
    response = client.get("/api/v1/models")
    assert response.status_code == 200
    assert "x-correlation-id" in response.headers
    assert "x-response-time-ms" in response.headers


# =============================================================================
# INGESTION & PIPELINE INTEGRATION TESTS
# =============================================================================
def test_ingest_stream_and_query_logs(client: TestClient):
    """Verify streaming log ingestion, Drain3 parsing, and log querying."""
    raw_logs = [
        "081109 203518 143 INFO dfs.DataNode$DataXceiver: Receiving block blk_-1608999614823707180 src: /10.250.19.102:54106 dest: /10.250.19.102:50010",
        "081109 203519 145 INFO dfs.DataNode$DataXceiver: Receiving block blk_-1608999614823707180 src: /10.250.19.102:54106 dest: /10.250.19.102:50010",
        "081109 203520 148 ERROR dfs.DataNode$DataXceiver: Verification failed for block blk_-1608999614823707180 checksum mismatch",
        "- 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.675872 R02-M1-N0-C:J12-U11 RAS KERNEL FATAL data storage interrupt",
    ]

    # Ingest batch
    ingest_res = client.post(
        "/api/v1/ingest/stream",
        json={"source_id": "test_stream", "lines": raw_logs},
    )
    assert ingest_res.status_code == 200
    job = ingest_res.json()
    assert job["status"] == "COMPLETED"
    assert job["total_records"] == 4
    assert job["valid_records"] == 4
    assert job["failed_records"] == 0
    job_id = job["job_id"]

    # Verify job query
    job_res = client.get(f"/api/v1/ingest/jobs/{job_id}")
    assert job_res.status_code == 200
    assert job_res.json()["job_id"] == job_id

    # Verify logs stored and searchable
    logs_res = client.get("/api/v1/logs?limit=10")
    assert logs_res.status_code == 200
    log_data = logs_res.json()
    assert log_data["total"] >= 4
    assert len(log_data["items"]) >= 4

    # Verify severity filter
    error_logs = client.get("/api/v1/logs?severity=ERROR").json()
    assert any("checksum mismatch" in item["message"] for item in error_logs["items"])


def test_templates_catalog(client: TestClient):
    """Verify Drain3 mined templates are exposed in the template catalog."""
    res = client.get("/api/v1/templates")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] > 0
    assert len(data["items"]) > 0
    template_ids = [t["template_id"] for t in data["items"]]
    assert len(set(template_ids)) == len(template_ids)


# =============================================================================
# ANOMALIES & EVIDENCE TESTS
# =============================================================================
def test_anomalies_and_evidence(client: TestClient):
    """Verify anomaly detection and detail retrieval with supporting evidence."""
    res = client.get("/api/v1/anomalies")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] > 0
    first_anom = data["items"][0]
    anomaly_id = first_anom["id"]

    # Detail query
    detail_res = client.get(f"/api/v1/anomalies/{anomaly_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == anomaly_id
    assert "supporting_evidence" in detail
    assert isinstance(detail["supporting_evidence"], list)

    # 404 test for non-existent anomaly
    not_found = client.get("/api/v1/anomalies/non_existent_id")
    assert not_found.status_code == 404


# =============================================================================
# ALERTS & INCIDENT OPERATIONS TESTS
# =============================================================================
def test_alert_lifecycle_and_actions(client: TestClient):
    """Verify alert listing, acknowledgement, and resolution workflows."""
    alerts_res = client.get("/api/v1/alerts")
    assert alerts_res.status_code == 200
    alerts = alerts_res.json()["items"]
    assert len(alerts) > 0
    target_alert = alerts[0]
    alert_id = target_alert["alert_id"]

    # 1. Acknowledge Alert
    ack_res = client.post(
        f"/api/v1/alerts/{alert_id}/action",
        json={"action": "ACKNOWLEDGE", "actor": "sre_lead", "note": "Acknowledged issue"},
    )
    assert ack_res.status_code == 200
    assert ack_res.json()["status"] == "ACKNOWLEDGED"

    # 2. Resolve Alert
    res_res = client.post(
        f"/api/v1/alerts/{alert_id}/action",
        json={"action": "RESOLVE", "actor": "sre_lead", "note": "Rebooted node and verified health"},
    )
    assert res_res.status_code == 200
    resolved_alert = res_res.json()
    assert resolved_alert["status"] == "RESOLVED"
    assert resolved_alert["resolved_by"] == "sre_lead"
    assert "Rebooted node" in resolved_alert["resolution_note"]


def test_incident_lifecycle(client: TestClient):
    """Verify incident retrieval and operational mitigation/resolution."""
    inc_res = client.get("/api/v1/incidents")
    assert inc_res.status_code == 200
    incidents = inc_res.json()["items"]
    if incidents:
        inc_id = incidents[0]["incident_id"]

        # Detail
        detail_res = client.get(f"/api/v1/incidents/{inc_id}")
        assert detail_res.status_code == 200
        assert detail_res.json()["incident_id"] == inc_id

        # Resolve incident
        action_res = client.post(
            f"/api/v1/incidents/{inc_id}/action",
            json={"action": "RESOLVE", "actor": "sre_lead", "summary_findings": "Storage nodes restored."},
        )
        assert action_res.status_code == 200
        assert action_res.json()["status"] == "RESOLVED"


# =============================================================================
# MODEL REGISTRY & BENCHMARKS TESTS
# =============================================================================
def test_models_registry(client: TestClient):
    """Verify /models registry returns all 5 detectors and their configurations."""
    res = client.get("/api/v1/models")
    assert res.status_code == 200
    models = res.json()
    assert len(models) == 5
    algorithms = [m["algorithm"] for m in models]
    assert "ModifiedZScoreDetector" in algorithms
    assert "IsolationForestDetector" in algorithms
    assert "DeepLogLSTM" in algorithms
    assert "LSTMAutoencoder" in algorithms
    assert "HybridEnsembleDetector" in algorithms


def test_models_benchmark(client: TestClient):
    """Verify /models/benchmark returns evaluation benchmark metrics."""
    res = client.get("/api/v1/models/benchmark")
    assert res.status_code == 200
    data = res.json()
    assert "dataset" in data
    assert "split_info" in data
    assert len(data["metrics"]) >= 4
    for metric in data["metrics"]:
        assert 0.0 <= metric["precision"] <= 1.0
        assert 0.0 <= metric["recall"] <= 1.0
        assert metric["inference_latency_ms"] > 0

