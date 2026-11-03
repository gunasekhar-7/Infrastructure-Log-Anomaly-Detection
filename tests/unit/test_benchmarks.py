"""Unit Tests for Benchmark Suite and Evaluation Metrics."""

import numpy as np
import pytest

from scripts.run_benchmark import BenchmarkRunner, evaluate_predictions, generate_markdown_report


def test_evaluate_predictions_standard():
    """Verify precision, recall, specificity, F1, and confusion matrix math."""
    y_true = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    scores = np.array([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9])
    threshold = 0.5

    metrics = evaluate_predictions(y_true, scores, threshold)
    assert metrics["threshold"] == 0.5
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["specificity"] == 1.0
    assert metrics["f1_score"] == 1.0
    assert metrics["accuracy"] == 1.0
    assert metrics["roc_auc"] == 1.0
    assert metrics["confusion_matrix"] == {"tp": 4, "fp": 0, "tn": 4, "fn": 0}


def test_evaluate_predictions_zero_division():
    """Verify zero-division handling when no samples exceed threshold."""
    y_true = np.array([0, 0, 1, 1])
    scores = np.array([0.1, 0.2, 0.3, 0.4])
    threshold = 0.9  # No positive predictions

    metrics = evaluate_predictions(y_true, scores, threshold)
    assert metrics["precision"] == 0.0
    assert metrics["recall"] == 0.0
    assert metrics["f1_score"] == 0.0
    assert metrics["confusion_matrix"]["tp"] == 0
    assert metrics["confusion_matrix"]["fp"] == 0


def test_benchmark_runner_data_loading():
    """Verify BenchmarkRunner loads and prepares features from the cleaned dataset."""
    runner = BenchmarkRunner(data_path="data/processed/hdfs_cleaned.csv")
    data = runner.load_and_preprocess(sequence_window_size=5)

    assert "vocab" in data
    assert "tabular" in data
    assert "sequential" in data
    assert "labels" in data
    assert data["split_sizes"]["train"] > 0
    assert data["split_sizes"]["val"] > 0
    assert data["split_sizes"]["test"] > 0

    X_train_tab, X_val_tab, X_test_tab = data["tabular"]
    assert X_train_tab.shape[0] == data["split_sizes"]["train"]
    assert X_test_tab.shape[0] == data["split_sizes"]["test"]


def test_generate_markdown_report(tmp_path):
    """Verify Markdown report generation format and structure."""
    mock_data = {
        "dataset": "Mock HDFS",
        "split_info": "Train: 10, Val: 5, Test: 5",
        "generated_at": "2026-11-03T12:00:00Z",
        "models": [
            {
                "model_name": "TestModel",
                "algorithm": "MockAlgo",
                "precision": 0.85,
                "recall": 0.90,
                "specificity": 0.95,
                "f1_score": 0.874,
                "roc_auc": 0.92,
                "pr_auc": 0.88,
                "training_time_sec": 0.5,
                "inf_latency_ms": 0.2,
                "throughput_sps": 5000.0,
            }
        ],
        "ablation_studies": {
            "sequence_window_length": [
                {
                    "sequence_length": 5,
                    "precision": 0.8,
                    "recall": 0.85,
                    "f1_score": 0.824,
                    "roc_auc": 0.9,
                    "train_time_sec": 1.0,
                    "inf_latency_ms": 0.3,
                }
            ],
            "top_k_candidates": [
                {
                    "top_k": 3,
                    "precision": 0.85,
                    "recall": 0.9,
                    "f1_score": 0.874,
                    "roc_auc": 0.92,
                    "pr_auc": 0.88,
                }
            ],
            "ensemble_weight_alpha": [
                {
                    "alpha_tabular": 0.4,
                    "alpha_sequential": 0.6,
                    "precision": 0.88,
                    "recall": 0.92,
                    "f1_score": 0.90,
                    "roc_auc": 0.95,
                    "pr_auc": 0.91,
                }
            ],
        },
    }

    out_file = tmp_path / "TEST_BENCHMARKS.md"
    generate_markdown_report(mock_data, output_md_path=out_file)

    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "# Empirical Benchmark Evaluation" in content
    assert "TestModel" in content
    assert "Ablation 1: Sequence Window Length" in content
    assert "Ablation 2: Top-$K$ Candidates" in content
    assert "Ablation 3: Hybrid Ensemble Weighting" in content

