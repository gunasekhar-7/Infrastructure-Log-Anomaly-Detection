"""Robustness, Concurrency, and Fuzz Testing for Log Ingestion & Inference."""

from concurrent.futures import ThreadPoolExecutor
import json
import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture(scope="module")
def client():
    """Module-scoped FastAPI TestClient."""
    with TestClient(app) as test_client:
        yield test_client


def test_extreme_line_length_handling(client: TestClient):
    """Verify system safely handles oversized single log messages (e.g. massive stacktraces) without crashing."""
    massive_trace = "081109 203518 143 ERROR dfs.DataNode: " + ("java.lang.NullPointerException: nested trace block " * 300)
    res = client.post(
        "/api/v1/ingest/stream",
        json={"source_id": "fuzz_massive_line", "lines": [massive_trace]},
        headers={"X-Bypass-Rate-Limit": "test-bypass"},
    )
    assert res.status_code == 200
    assert res.json()["valid_records"] == 1


def test_unicode_and_special_character_resilience(client: TestClient):
    """Verify system handles non-ASCII characters, Asian scripts, emojis, and symbols gracefully."""
    multilingual_logs = [
        "081109 203518 143 WARN auth.Service: ⚠️ 未知のユーザーログイン試行 (Unknown login attempt)",
        "081109 203519 144 ERROR k8s.Controller: 💥 Pod CrashLoopBackOff: 컨테이너 실행 실패 (Failed container)",
        "081109 203520 145 INFO mesh.Envoy: 🚀 TLS 握手成功 (Handshake completed)",
        "- 1117838570 2005.06.03 R02-M1-N0 2005-06-03 RAS KERNEL INFO ⚡ Überhitzungswarnung: Temperatur > 85°C",
    ]
    res = client.post(
        "/api/v1/ingest/stream",
        json={"source_id": "fuzz_unicode", "lines": multilingual_logs},
        headers={"X-Bypass-Rate-Limit": "test-bypass"},
    )
    assert res.status_code == 200
    assert res.json()["valid_records"] == len(multilingual_logs)


def test_interleaved_json_and_syslog_streams(client: TestClient):
    """Verify parser seamlessly handles mixed JSON payloads and standard syslog in a single batch."""
    mixed_format_logs = [
        json.dumps({
            "timestamp": "2026-11-03T18:00:00Z",
            "level": "INFO",
            "host": "auth-svc-prod-01",
            "service": "authentication",
            "message": "User token validated successfully",
        }),
        "081109 203518 143 INFO dfs.DataNode$DataXceiver: Receiving block blk_-99999 src: /10.250.1.1:54106 dest: /10.250.1.1:50010",
        "- 1117838570 2005.06.03 R02-M1-N0 2005-06-03 RAS KERNEL INFO generating core.999",
    ]
    res = client.post(
        "/api/v1/ingest/stream",
        json={"source_id": "fuzz_mixed_formats", "lines": mixed_format_logs},
        headers={"X-Bypass-Rate-Limit": "test-bypass"},
    )
    assert res.status_code == 200
    assert res.json()["valid_records"] == 3


def test_concurrent_ingestion_safety(client: TestClient):
    """Verify concurrent ingestion batches do not cause SQLite/PostgreSQL locking deadlocks."""
    def send_batch(thread_id: int):
        lines = [
            f"081109 203518 143 INFO dfs.DataNode: Thread {thread_id} event 1",
            f"081109 203519 144 INFO dfs.DataNode: Thread {thread_id} event 2",
        ]
        return client.post(
            "/api/v1/ingest/stream",
            json={"source_id": f"concurrent_t{thread_id}", "lines": lines},
            headers={"X-Bypass-Rate-Limit": "test-bypass"},
        )

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(send_batch, i) for i in range(10)]
        results = [f.result() for f in futures]

    assert all(r.status_code == 200 for r in results)
    assert all(r.json()["valid_records"] == 2 for r in results)

