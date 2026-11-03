"""Unit tests for dataset parsing, normalization, and leakage-free splitting."""

import json
from pathlib import Path
import pytest
import pandas as pd

from src.ingestion.dataset_engineering import (
    parse_hdfs_line,
    parse_bgl_line,
    BenchmarkDataPipeline
)


def test_parse_hdfs_line_valid() -> None:
    """Verify parsing of standard HDFS log line with block ID extraction."""
    raw_line = "081109 203615 148 INFO dfs.DataNode$PacketResponder: PacketResponder 1 for block blk_38865049064139660 terminating"
    parsed = parse_hdfs_line(0, raw_line)

    assert parsed is not None
    assert parsed["is_valid"] is True
    assert parsed["level"] == "INFO"
    assert parsed["component"] == "dfs.DataNode$PacketResponder"
    assert parsed["block_id"] == "blk_38865049064139660"
    assert parsed["timestamp"] == "2008-11-09T20:36:15+00:00"


def test_parse_hdfs_line_invalid_fallback() -> None:
    """Verify non-standard HDFS line handles failure gracefully."""
    raw_line = "Corrupted non-standard log without timestamp"
    parsed = parse_hdfs_line(1, raw_line)

    assert parsed is not None
    assert parsed["is_valid"] is False
    assert parsed["timestamp"] is None
    assert parsed["block_id"] == "unknown"


def test_parse_bgl_line_normal() -> None:
    """Verify parsing of normal BGL log line."""
    raw_line = "- 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.675872 R02-M1-N0-C:J12-U11 RAS KERNEL INFO instruction cache parity error corrected"
    parsed = parse_bgl_line(0, raw_line)

    assert parsed is not None
    assert parsed["is_valid"] is True
    assert parsed["raw_label"] == "-"
    assert parsed["label"] == "Normal"
    assert parsed["level"] == "INFO"
    assert parsed["node"] == "R02-M1-N0-C:J12-U11"
    assert parsed["component"] == "KERNEL"
    assert parsed["timestamp"] is not None


def test_parse_bgl_line_anomaly() -> None:
    """Verify parsing of anomalous BGL log line with alert label."""
    raw_line = "FATAL 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.675872 R02-M1-N0-C:J12-U11 RAS KERNEL FATAL hardware failure"
    parsed = parse_bgl_line(0, raw_line)

    assert parsed is not None
    assert parsed["is_valid"] is True
    assert parsed["raw_label"] == "FATAL"
    assert parsed["label"] == "Anomaly"


def test_hdfs_data_pipeline_leakage_free() -> None:
    """Verify HDFS processing creates splits with zero block ID overlap."""
    pipeline = BenchmarkDataPipeline()
    df, manifest = pipeline.load_and_process_hdfs()

    assert len(df) == 2000
    assert manifest["leakage_check_passed"] is True

    # Assert sets of block IDs are strictly disjoint
    train_blocks = set(df[df["split"] == "train"]["block_id"])
    val_blocks = set(df[df["split"] == "val"]["block_id"])
    test_blocks = set(df[df["split"] == "test"]["block_id"])

    assert len(train_blocks & test_blocks) == 0
    assert len(train_blocks & val_blocks) == 0
    assert len(val_blocks & test_blocks) == 0


def test_bgl_data_pipeline_chronological() -> None:
    """Verify BGL processing maintains strict temporal split ordering."""
    pipeline = BenchmarkDataPipeline()
    df, manifest = pipeline.load_and_process_bgl()

    assert len(df) == 2000
    assert manifest["leakage_check_passed"] is True

    train_indices = df[df["split"] == "train"]["line_idx"]
    val_indices = df[df["split"] == "val"]["line_idx"]
    test_indices = df[df["split"] == "test"]["line_idx"]

    assert train_indices.max() < val_indices.min()
    assert val_indices.max() < test_indices.min()
