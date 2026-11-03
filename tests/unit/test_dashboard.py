"""Unit Tests for Streamlit Dashboard Client and View Integration."""

import pytest

from src.dashboard.api_client import DashboardAPIClient
from src.dashboard.views import (
    render_anomaly_inspector_view,
    render_log_explorer_view,
    render_model_benchmarks_view,
    render_overview_view,
    render_traffic_simulator_view,
    render_triage_board_view,
)


@pytest.fixture
def api_client():
    """Provides a initialized DashboardAPIClient."""
    return DashboardAPIClient()


def test_client_health_and_models(api_client: DashboardAPIClient):
    """Verify API client retrieves system health and model registry."""
    health = api_client.get_health()
    assert health["status"] in ("UP", "DEGRADED")
    assert "database" in health

    models = api_client.get_models()
    assert len(models) == 5
    names = [m["name"] for m in models]
    assert "Hybrid Ensemble" in names


def test_client_benchmarks(api_client: DashboardAPIClient):
    """Verify API client retrieves model benchmark evaluations."""
    benchmarks = api_client.get_benchmarks()
    assert "dataset" in benchmarks
    assert "split_info" in benchmarks
    assert len(benchmarks["metrics"]) >= 4


def test_client_ingestion_and_queries(api_client: DashboardAPIClient):
    """Verify API client streaming ingestion and subsequent querying."""
    logs = [
        "081109 203518 143 INFO dfs.DataNode$DataXceiver: Test log line for client unit test",
        "081109 203520 148 ERROR dfs.DataNode$DataXceiver: Anomaly line checksum failed",
    ]
    res = api_client.ingest_stream(logs, source_id="test_unit_client")
    assert res["status"] == "COMPLETED"
    assert res["valid_records"] == 2

    # Query logs
    q_logs = api_client.query_logs(limit=10)
    assert q_logs["total"] >= 2
    assert len(q_logs["items"]) >= 2

    # Query anomalies
    anoms = api_client.query_anomalies(limit=10)
    assert "items" in anoms

    # Query alerts
    alerts = api_client.query_alerts(limit=10)
    assert "items" in alerts

    # If an alert exists, test action
    if alerts["items"]:
        aid = alerts["items"][0]["alert_id"]
        ack = api_client.post_alert_action(aid, "ACKNOWLEDGE", actor="test_runner", note="Unit test ack")
        assert ack["status"] == "ACKNOWLEDGED"


def test_view_function_signatures():
    """Verify view render functions are callable and properly structured."""
    for fn in [
        render_overview_view,
        render_log_explorer_view,
        render_anomaly_inspector_view,
        render_triage_board_view,
        render_model_benchmarks_view,
        render_traffic_simulator_view,
    ]:
        assert callable(fn)

