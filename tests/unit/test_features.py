"""Unit tests for Feature Extraction and Preprocessing Pipeline."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import pytest

from src.ingestion.models import LogEvent, LogSeverity
from src.parsing.models import ParsedLogEvent
from src.features import (
    FeaturePipeline,
    FrequencyFeatureExtractor,
    SequenceFeatureExtractor,
    calculate_entropy,
)


def create_sample_parsed_events(count: int = 50, has_errors: bool = True) -> list[ParsedLogEvent]:
    """Helper creating a synthetic chronological stream of ParsedLogEvents."""
    base_time = datetime(2026, 11, 3, 12, 0, 0, tzinfo=timezone.utc)
    events = []
    templates = ["E1", "E2", "E3", "E4"]

    for i in range(count):
        ts = base_time + timedelta(seconds=i * 2)
        tmpl = templates[i % len(templates)]
        sev = LogSeverity.ERROR if (has_errors and i % 10 == 0) else LogSeverity.INFO
        ev = ParsedLogEvent(
            event_id=f"ev_{i}",
            timestamp=ts,
            host="node-01",
            service="dfs",
            component="DataNode",
            severity=sev,
            message=f"Message {i} for template {tmpl}",
            raw_log=f"raw {i}",
            source_id="test",
            template_id=tmpl,
            template_text=f"Template pattern for {tmpl}",
            parameters=[str(i)],
            attributes={"block_id": f"blk_{i // 5}", "is_anomaly": (sev == LogSeverity.ERROR)},
        )
        events.append(ev)
    return events


def test_calculate_entropy() -> None:
    """Verify Shannon entropy calculation."""
    # Single element distribution -> 0 entropy
    assert calculate_entropy([10]) == 0.0

    # Uniform 2-element distribution -> exactly 1.0 bit
    assert round(calculate_entropy([10, 10]), 4) == 1.0


def test_frequency_feature_extractor_time_windows() -> None:
    """Verify frequency feature extraction over chronological sliding windows."""
    events = create_sample_parsed_events(count=30)
    extractor = FrequencyFeatureExtractor(
        window_size_sec=20,
        step_size_sec=10,
        known_templates=["E1", "E2", "E3", "E4"],
    )

    df, records = extractor.extract_from_events(events)

    assert not df.empty
    assert len(records) > 0
    assert "event_count" in df.columns
    assert "error_rate" in df.columns
    assert "template_entropy" in df.columns
    assert "tmpl_E1" in df.columns
    assert df["event_count"].min() > 0


def test_frequency_feature_extractor_blocks() -> None:
    """Verify grouping by discrete block identifiers."""
    events = create_sample_parsed_events(count=25)
    extractor = FrequencyFeatureExtractor(known_templates=["E1", "E2"])

    df, records = extractor.extract_from_blocks(events, block_key="block_id")

    assert len(df) == 5  # 25 events / 5 per block = 5 blocks
    assert all(r.window_id.startswith("block_blk_") for r in records)


def test_sequence_feature_extractor() -> None:
    """Verify sequential sliding window generation and padding."""
    vocab = {"<PAD>": 0, "<UNK>": 1, "E1": 2, "E2": 3, "E3": 4, "E4": 5}
    extractor = SequenceFeatureExtractor(vocabulary=vocab, window_size=5, step_size=1)

    events = create_sample_parsed_events(count=15)
    samples = extractor.extract_from_event_stream(events)

    assert len(samples) == 10  # 15 - 5 = 10 sliding windows
    first = samples[0]
    assert len(first.sequence_templates) == 5
    assert len(first.sequence_indices) == 5
    assert first.next_template == "E2"  # (0,1,2,3,4) -> next is 5th item (index 5 % 4 = 1 -> E2)

    X, y = extractor.to_tensors(samples)
    assert X.shape == (10, 5)
    assert y.shape == (10,)
    assert X.dtype == np.int64


def test_sequence_feature_extractor_block_padding() -> None:
    """Verify sequence padding when block length is shorter than window size."""
    vocab = {"<PAD>": 0, "<UNK>": 1, "E1": 2, "E2": 3}
    extractor = SequenceFeatureExtractor(vocabulary=vocab, window_size=10)

    # 3 events in block < window_size 10
    events = create_sample_parsed_events(count=3)
    samples = extractor.extract_from_blocks(events, block_key="block_id")

    assert len(samples) >= 1
    sample = samples[0]
    assert len(sample.sequence_indices) == 10
    # First tokens should be PAD
    assert sample.sequence_indices[0] == 0


def test_feature_pipeline_fit_transform_and_persistence(tmp_path: Path) -> None:
    """Verify FeaturePipeline fits scaler, transforms unseen data, and serializes state."""
    vocab = {"<PAD>": 0, "<UNK>": 1, "E1": 2, "E2": 3, "E3": 4, "E4": 5}
    pipeline = FeaturePipeline(
        vocabulary=vocab,
        window_size_sec=30,
        step_size_sec=15,
        sequence_window_size=10,
        version="v1.0-test",
    )

    train_events = create_sample_parsed_events(count=60)
    test_events = create_sample_parsed_events(count=30)

    # Fit and transform on training data
    X_train, df_train, _ = pipeline.fit_transform_tabular(train_events)
    assert pipeline.is_fitted is True
    assert X_train.shape[0] == len(df_train)
    # Scaled training data should have approximately mean 0
    assert abs(np.mean(X_train[:, 0])) < 1e-4

    # Transform test data using fitted scaler (zero leakage)
    X_test, df_test, _ = pipeline.transform_tabular(test_events)
    assert X_test.shape[1] == X_train.shape[1]

    # Save pipeline state
    out_dir = tmp_path / "pipeline_artifact"
    pipeline.save(out_dir)
    assert (out_dir / "scaler.joblib").exists()
    assert (out_dir / "metadata.json").exists()

    # Reload pipeline and verify transform reproducibility
    reloaded = FeaturePipeline.load(out_dir)
    assert reloaded.version == "v1.0-test"
    assert reloaded.is_fitted is True
    X_test_reloaded, _, _ = reloaded.transform_tabular(test_events)
    np.testing.assert_array_almost_equal(X_test, X_test_reloaded)
