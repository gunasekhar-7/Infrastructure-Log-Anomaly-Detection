"""Unit tests for Baseline Anomaly Detection Models."""

from pathlib import Path
import numpy as np
import pytest

from src.exceptions import ModelNotTrainedError
from src.models import (
    FrequencyAnomalyDetector,
    IsolationForestDetector,
    StatisticalDetector,
    compare_models,
    evaluate_detector_on_splits,
)


@pytest.fixture
def synthetic_data() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Generate synthetic train (normal only), val, and test splits with injected anomalies."""
    rng = np.random.default_rng(seed=42)

    # 200 normal training samples, 5 features
    X_train = rng.normal(loc=0.0, scale=1.0, size=(200, 5))

    # 50 validation samples (40 normal, 10 anomalies with large shift)
    X_val_norm = rng.normal(loc=0.0, scale=1.0, size=(40, 5))
    X_val_anom = rng.normal(loc=5.0, scale=1.5, size=(10, 5))
    X_val = np.vstack([X_val_norm, X_val_anom])
    y_val = np.array([0] * 40 + [1] * 10)

    # 50 test samples (40 normal, 10 anomalies)
    X_test_norm = rng.normal(loc=0.0, scale=1.0, size=(40, 5))
    X_test_anom = rng.normal(loc=5.0, scale=1.5, size=(10, 5))
    X_test = np.vstack([X_test_norm, X_test_anom])
    y_test = np.array([0] * 40 + [1] * 10)

    return X_train, X_val, y_val, X_test, y_test


def test_statistical_detector(synthetic_data: tuple, tmp_path: Path) -> None:
    """Verify StatisticalDetector training, scoring, outlier isolation, and persistence."""
    X_train, X_val, y_val, X_test, y_test = synthetic_data

    detector = StatisticalDetector(z_threshold=3.0)

    # Predict before fit raises exception
    with pytest.raises(ModelNotTrainedError):
        detector.predict(X_test)

    detector.fit(X_train)
    assert detector.is_fitted is True

    scores = detector.score(X_test)
    assert scores.shape == (50,)
    assert np.all((scores >= 0.0) & (scores <= 1.0))

    # Anomalies (samples 40..49) must have higher scores than normal samples
    normal_scores = scores[:40]
    anomaly_scores = scores[40:]
    assert np.mean(anomaly_scores) > np.mean(normal_scores)

    # Threshold calibration
    detector.calibrate_threshold(detector.score(X_val), val_labels=y_val)
    assert 0.0 < detector.threshold < 1.0

    metrics = detector.evaluate(X_test, y_test)
    assert metrics["f1"] > 0.7
    assert metrics["roc_auc"] > 0.8

    # Serialization
    model_path = tmp_path / "stat_model.json"
    detector.save(model_path)
    assert model_path.exists()

    reloaded = StatisticalDetector.load(model_path)
    assert reloaded.is_fitted is True
    np.testing.assert_array_almost_equal(reloaded.score(X_test), scores)


def test_isolation_forest_detector(synthetic_data: tuple, tmp_path: Path) -> None:
    """Verify IsolationForestDetector training, scoring, evaluation, and persistence."""
    X_train, X_val, y_val, X_test, y_test = synthetic_data

    detector = IsolationForestDetector(n_estimators=50, random_state=42)
    detector.fit(X_train)

    scores = detector.score(X_test)
    assert scores.shape == (50,)
    assert np.all((scores >= 0.0) & (scores <= 1.0))

    # Anomalous samples must have higher scores than normal
    assert np.mean(scores[40:]) > np.mean(scores[:40])

    detector.calibrate_threshold(detector.score(X_val), val_labels=y_val)
    metrics = detector.evaluate(X_test, y_test)
    assert metrics["f1"] > 0.7
    assert metrics["precision"] > 0.5
    assert metrics["recall"] > 0.5

    # Serialization
    model_path = tmp_path / "iso_forest"
    detector.save(model_path)
    assert (tmp_path / "iso_forest.joblib").exists()
    assert (tmp_path / "iso_forest.json").exists()

    reloaded = IsolationForestDetector.load(model_path)
    assert reloaded.is_fitted is True
    np.testing.assert_array_almost_equal(reloaded.score(X_test), scores)


def test_frequency_anomaly_detector() -> None:
    """Verify FrequencyAnomalyDetector on template sequences and state transitions."""
    detector = FrequencyAnomalyDetector()

    # Normal sequences consistently follow E1 -> E2 -> E3
    normal_seqs = [["E1", "E2", "E3"] for _ in range(50)]
    detector.fit_from_sequences(normal_seqs)

    # Normal test sequence
    norm_score = detector.score_sequence(["E1", "E2", "E3"])
    assert norm_score == 0.0

    # Anomalous sequence with rare template E99 and unexpected transition E1 -> E99
    anom_score = detector.score_sequence(["E1", "E99", "E3"])
    assert anom_score > 0.5


def test_compare_models_harness(synthetic_data: tuple) -> None:
    """Verify multi-model comparison returns structured metrics table."""
    X_train, X_val, y_val, X_test, y_test = synthetic_data

    models = [
        StatisticalDetector(z_threshold=3.0),
        IsolationForestDetector(n_estimators=30, random_state=42),
    ]

    results_df = compare_models(
        models=models,
        X_train=X_train,
        X_val=X_val,
        y_val=y_val,
        X_test=X_test,
        y_test=y_test,
    )

    assert len(results_df) == 2
    assert "precision" in results_df.columns
    assert "recall" in results_df.columns
    assert "f1" in results_df.columns
    assert "roc_auc" in results_df.columns

