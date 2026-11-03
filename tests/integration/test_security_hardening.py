"""Integration Tests for Security Hardening, Rate Limiting, Input Sanitization & Telemetry."""

import io
import pytest
from fastapi.testclient import TestClient

from config.settings import settings
from src.api.main import app


@pytest.fixture(scope="module")
def client():
    """Module-scoped FastAPI TestClient."""
    with TestClient(app) as test_client:
        yield test_client


# =============================================================================
# 1. SECURITY HEADERS VERIFICATION
# =============================================================================
def test_security_headers_present(client: TestClient):
    """Verify OWASP-recommended security headers are injected into HTTP responses."""
    res = client.get("/healthz")
    assert res.status_code == 200
    headers = res.headers

    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"
    assert "mode=block" in headers.get("x-xss-protection", "")
    assert "default-src 'self'" in headers.get("content-security-policy", "")
    assert "max-age=" in headers.get("strict-transport-security", "")


# =============================================================================
# 2. RATE LIMITING MIDDLEWARE
# =============================================================================
def test_rate_limiting_enforcement(client: TestClient):
    """Verify rate limiter issues 429 when quota is exceeded from the same IP."""
    # Use client with custom IP header
    headers = {"X-Forwarded-For": "203.0.113.195"}

    # We send requests until limit is reached or 429 is encountered
    hit_429 = False
    for _ in range(settings.RATE_LIMIT_PER_MINUTE + 5):
        res = client.get("/api/v1/models", headers=headers)
        if res.status_code == 429:
            hit_429 = True
            assert "Retry-After" in res.headers
            assert res.json()["error"] == "Too Many Requests"
            break

    assert hit_429, "Expected rate limiter to return 429 after exceeding quota"


def test_rate_limiting_bypass(client: TestClient):
    """Verify internal bypass header allows emergency/testing traffic through."""
    headers = {
        "X-Forwarded-For": "203.0.113.195",
        "X-Bypass-Rate-Limit": "test-bypass",
    }
    res = client.get("/api/v1/models", headers=headers)
    assert res.status_code == 200


# =============================================================================
# 3. INPUT SANITIZATION & BOUNDARY GUARDRAILS
# =============================================================================
def test_ingest_batch_size_guardrail(client: TestClient):
    """Verify requests exceeding MAX_INGEST_BATCH_SIZE are rejected with 413."""
    oversized_lines = ["081109 203518 143 INFO dfs.DataNode: dummy log line"] * (settings.MAX_INGEST_BATCH_SIZE + 1)
    res = client.post(
        "/api/v1/ingest/stream",
        json={"source_id": "test_oversized", "lines": oversized_lines},
        headers={"X-Bypass-Rate-Limit": "test-bypass"},
    )
    assert res.status_code == 413
    assert "exceeds maximum permitted" in res.json()["detail"]


def test_input_sanitization_null_bytes(client: TestClient):
    """Verify null bytes and empty lines are safely sanitized without crashing."""
    dirty_lines = [
        "081109 203518 143 INFO dfs.DataNode: normal line with\x00 null byte removed",
        "   ",  # empty line
        "081109 203519 144 INFO dfs.DataNode: clean second line",
    ]
    res = client.post(
        "/api/v1/ingest/stream",
        json={"source_id": "test_sanitization", "lines": dirty_lines},
        headers={"X-Bypass-Rate-Limit": "test-bypass"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "COMPLETED"
    assert data["total_records"] == 2  # The empty line was pruned, 2 valid lines ingested


def test_file_upload_extension_validation(client: TestClient):
    """Verify malicious or unsupported file extensions are rejected with 400."""
    fake_exe = io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00")
    files = {"file": ("malicious_payload.exe", fake_exe, "application/octet-stream")}
    res = client.post(
        "/api/v1/ingest/upload",
        files=files,
        headers={"X-Bypass-Rate-Limit": "test-bypass"},
    )
    assert res.status_code == 400
    assert "Unsupported file extension" in res.json()["detail"]


# =============================================================================
# 4. PROMETHEUS TELEMETRY EXPORT
# =============================================================================
def test_prometheus_custom_metrics_exported(client: TestClient):
    """Verify custom metrics are registered and scraped at /metrics."""
    res = client.get("/metrics")
    assert res.status_code == 200
    text = res.text

    assert "logpulse_http_requests_total" in text
    assert "logpulse_drain3_templates_count" in text
    assert "logpulse_anomalies_detected_total" in text

