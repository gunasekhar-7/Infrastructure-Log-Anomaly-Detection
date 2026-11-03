"""Unit tests for Drain3 Log Parsing and Template Mining."""

from pathlib import Path
import pytest

from src.ingestion.models import LogEvent, LogSeverity
from src.parsing import (
    DrainParser,
    LogTemplate,
    ParsedLogEvent,
    ParserEvaluator,
    TemplateCatalog,
    pre_mask_message,
)


def test_pre_mask_message() -> None:
    """Verify masking rules replace dynamic variables with tokens."""
    msg = "Node 192.168.1.10:8080 accessed block blk_123456 at memory 0x7ffd12"
    masked = pre_mask_message(msg)

    assert "<*IP*>" in masked
    assert "<*BLOCK*>" in masked
    assert "<*HEX*>" in masked
    assert "192.168.1.10:8080" not in masked
    assert "blk_123456" not in masked


def test_template_catalog_registration(tmp_path: Path) -> None:
    """Verify template catalog registers clusters, tracks counts, and persists."""
    catalog_file = tmp_path / "catalog.json"
    catalog = TemplateCatalog(persistence_path=catalog_file)

    t1, is_unseen1 = catalog.register_or_update(1, "Node <*> failed after <*> retries", ["10.0.0.1", "3"])
    assert is_unseen1 is True
    assert t1.template_id == "E1"
    assert t1.occurrence_count == 1

    t2, is_unseen2 = catalog.register_or_update(1, "Node <*> failed after <*> retries", ["10.0.0.2", "4"])
    assert is_unseen2 is False
    assert t2.occurrence_count == 2

    # Test persistence save and reload
    catalog.save()
    assert catalog_file.exists()

    reloaded = TemplateCatalog(persistence_path=catalog_file)
    assert reloaded.total_templates == 1
    assert reloaded.get_template("E1").occurrence_count == 2


def test_drain_parser_parameter_extraction() -> None:
    """Verify Drain3 clusters logs into wildcards and extracts parameters."""
    parser = DrainParser(sim_th=0.5, depth=4)

    # First log
    tmpl_id1, t1, p1, unseen1 = parser.parse_message("Node 192.168.1.10 failed after 3 retries")
    assert unseen1 is True

    # Second log with different dynamic values
    tmpl_id2, t2, p2, unseen2 = parser.parse_message("Node 10.0.0.1 failed after 5 retries")

    # They should merge into the same canonical cluster
    assert tmpl_id1 == tmpl_id2
    assert "Node" in t2 and "failed after" in t2 and "retries" in t2
    assert "<*>" in t2
    assert "10.0.0.1" in p2
    assert "5" in p2


def test_drain_parser_event_conversion() -> None:
    """Verify converting LogEvent to ParsedLogEvent."""
    parser = DrainParser()
    event = LogEvent(
        message="PacketResponder 1 for block blk_38865049064139660 terminating",
        raw_log="081109 203615 148 INFO dfs.DataNode: PacketResponder 1 for block blk_38865049064139660 terminating",
        severity=LogSeverity.INFO,
        host="node-01",
        service="hdfs",
        component="DataNode",
    )

    parsed = parser.parse_event(event)
    assert isinstance(parsed, ParsedLogEvent)
    assert parsed.template_id.startswith("E")
    assert "PacketResponder" in parsed.template_text
    assert parsed.host == "node-01"
    assert parsed.severity == LogSeverity.INFO


def test_drain_parser_vocabulary() -> None:
    """Verify template vocabulary generation for ML sequence models."""
    parser = DrainParser()
    parser.parse_message("Service started successfully on port 8000")
    parser.parse_message("Connection established to database")

    vocab = parser.get_template_vocabulary()
    assert "<PAD>" in vocab and vocab["<PAD>"] == 0
    assert "<UNK>" in vocab and vocab["<UNK>"] == 1
    assert "E1" in vocab
    assert "E2" in vocab


def test_parser_evaluator() -> None:
    """Verify parser evaluation computes throughput and stability metrics."""
    parser = DrainParser()
    evaluator = ParserEvaluator(parser)

    events = [
        LogEvent(message=f"Processing job {i} on worker 1", raw_log="raw")
        for i in range(100)
    ]

    metrics = evaluator.evaluate_stream(events)
    assert metrics["total_logs_evaluated"] == 100
    assert metrics["throughput_logs_per_sec"] > 500
    assert metrics["unique_templates_mined"] >= 1
    assert metrics["template_stability_metric"] in ("STABLE", "GROWING")

