"""Unit tests for the Log Ingestion Subsystem."""

import json
from pathlib import Path
import pytest

from src.exceptions import IngestionError
from src.ingestion import (
    DeadLetterQueue,
    DuplicateDetector,
    LogFormat,
    LogIngestionEngine,
    LogSeverity,
    ParsingStatus,
    detect_file_format,
    detect_line_format,
    normalize_severity,
    normalize_timestamp,
    sanitize_line,
    validate_file,
)


def test_validate_file_success(tmp_path: Path) -> None:
    """Verify file validation succeeds on valid log file."""
    f = tmp_path / "app.log"
    f.write_text("sample log line\n", encoding="utf-8")
    assert validate_file(f) == f.resolve()


def test_validate_file_missing(tmp_path: Path) -> None:
    """Verify validation fails when file is missing."""
    f = tmp_path / "non_existent.log"
    with pytest.raises(IngestionError, match="does not exist"):
        validate_file(f)


def test_validate_file_invalid_extension(tmp_path: Path) -> None:
    """Verify validation rejects unpermitted file extensions."""
    f = tmp_path / "payload.exe"
    f.write_bytes(b"binary data")
    with pytest.raises(IngestionError, match="Unsupported file extension"):
        validate_file(f)


def test_sanitize_line() -> None:
    """Verify null bytes stripped and max length enforced."""
    dirty_line = "Error in service\x00\x00 occurred\r\n"
    assert sanitize_line(dirty_line) == "Error in service occurred"

    oversized = "A" * 40_000
    sanitized = sanitize_line(oversized)
    assert len(sanitized) <= 33_000
    assert sanitized.endswith("...[TRUNCATED]")


def test_detect_line_format() -> None:
    """Verify format detection across diverse log types."""
    json_line = '{"timestamp": "2026-11-03T10:00:00Z", "level": "ERROR", "message": "DB connection timeout"}'
    hdfs_line = "081109 203615 148 INFO dfs.DataNode$PacketResponder: PacketResponder 1 terminating"
    bgl_line = "- 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.675872 R02-M1-N0-C:J12-U11 RAS KERNEL INFO instruction cache parity error"
    app_line = "2026-11-03 10:15:30 [WARN] [payment-svc] Insufficient funds error"
    syslog_line = "Oct 11 22:14:15 myhost sshd[1234]: Failed password for root"
    raw_line = "random unstructured message"

    assert detect_line_format(json_line) == LogFormat.JSON
    assert detect_line_format(hdfs_line) == LogFormat.HDFS
    assert detect_line_format(bgl_line) == LogFormat.BGL
    assert detect_line_format(app_line) == LogFormat.APP_LOG
    assert detect_line_format(syslog_line) == LogFormat.SYSLOG
    assert detect_line_format(raw_line) == LogFormat.RAW


def test_normalize_severity() -> None:
    """Verify normalization of severity strings."""
    assert normalize_severity("INFO") == LogSeverity.INFO
    assert normalize_severity("warn") == LogSeverity.WARN
    assert normalize_severity("WARNING") == LogSeverity.WARN
    assert normalize_severity("error") == LogSeverity.ERROR
    assert normalize_severity("FATAL") == LogSeverity.FATAL
    assert normalize_severity("CRITICAL") == LogSeverity.FATAL
    assert normalize_severity("unknown") == LogSeverity.INFO


def test_normalize_timestamp() -> None:
    """Verify normalization of different timestamp formats."""
    # Epoch seconds
    ts1 = normalize_timestamp(1700000000)
    assert ts1.year == 2023

    # ISO string
    ts2 = normalize_timestamp("2026-11-03T14:30:00Z")
    assert ts2.year == 2026 and ts2.hour == 14 and ts2.minute == 30

    # HDFS format
    ts3 = normalize_timestamp("081109 203615")
    assert ts3.year == 2008 and ts3.month == 11 and ts3.day == 9


def test_duplicate_detector() -> None:
    """Verify duplicate detection and LRU eviction."""
    detector = DuplicateDetector(capacity=2)
    assert detector.is_duplicate("host1", "svc1", "msg1", 100.0) is False
    # Same content and timestamp
    assert detector.is_duplicate("host1", "svc1", "msg1", 100.0) is True
    # Different message
    assert detector.is_duplicate("host1", "svc1", "msg2", 100.0) is False
    # Third entry evicts first
    assert detector.is_duplicate("host1", "svc1", "msg3", 100.0) is False
    # msg1 should now be re-evaluated as not duplicate after eviction
    assert detector.is_duplicate("host1", "svc1", "msg1", 100.0) is False


def test_dead_letter_queue(tmp_path: Path) -> None:
    """Verify dead-letter queue records invalid records with diagnostic reasons."""
    dump_file = tmp_path / "dead_letter.log"
    dlq = DeadLetterQueue(max_size=10, dump_file=dump_file)

    rec = dlq.record_failure(
        raw_content="corrupt log data",
        failure_reason="Malformed format",
        source_id="test_stream"
    )

    assert rec.raw_content == "corrupt log data"
    assert rec.failure_reason == "Malformed format"
    assert dlq.total_failures == 1
    assert dump_file.exists()
    assert "Malformed format" in dump_file.read_text(encoding="utf-8")


def test_ingestion_engine_hdfs_file() -> None:
    """Verify ingesting HDFS raw benchmark file."""
    engine = LogIngestionEngine(enable_deduplication=False)
    hdfs_file = Path("data/raw/hdfs/HDFS_2k.log")

    events, stats = engine.ingest_file(hdfs_file)

    assert len(events) == 2000
    assert stats.total_records == 2000
    assert stats.valid_records == 2000
    assert stats.invalid_records == 0
    assert stats.throughput_eps > 500  # High throughput expectation

    # Inspect first parsed event
    ev = events[0]
    assert ev.severity == LogSeverity.INFO
    assert ev.component == "dfs.DataNode$PacketResponder"
    assert "blk_38865049064139660" in ev.attributes.get("block_id", "")
    assert ev.parsing_status == ParsingStatus.VALID


def test_ingestion_engine_json_records() -> None:
    """Verify ingesting structured JSON log records."""
    engine = LogIngestionEngine()
    records = [
        {"timestamp": "2026-11-03T12:00:00Z", "level": "ERROR", "service": "auth-svc", "host": "auth-01", "message": "Invalid JWT token"},
        {"timestamp": "2026-11-03T12:00:01Z", "level": "INFO", "service": "auth-svc", "host": "auth-01", "message": "User login success"},
    ]

    events, stats = engine.ingest_json_records(records, source_id="auth_service")

    assert len(events) == 2
    assert stats.valid_records == 2
    assert events[0].severity == LogSeverity.ERROR
    assert events[0].service == "auth-svc"
    assert events[0].host == "auth-01"
    assert events[0].message == "Invalid JWT token"

