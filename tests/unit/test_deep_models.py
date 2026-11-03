"""Unit tests for Advanced Sequential Deep Learning Models (DeepLog & LSTM Autoencoder)."""

from pathlib import Path
import numpy as np
import pytest
import torch

from src.models import (
    AnomalyEnsembleDetector,
    DeepLogDetector,
    IsolationForestDetector,
    LSTMAutoencoderDetector,
)


@pytest.fixture
def sequence_data() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Synthetic normal sequences following steady-state patterns [2, 3, 4, 5] -> 6."""
    rng = np.random.default_rng(seed=42)

    # Normal sequences: repeated cycle of tokens 2 -> 3 -> 4 -> 5 -> 6
    seq_list = []
    y_list = []
    base_pattern = [2, 3, 4, 5, 6, 2, 3, 4, 5, 6]

    for _ in range(100):
        start_idx = rng.integers(0, 5)
        pat = (base_pattern * 3)[start_idx : start_idx + 6]
        seq_list.append(pat[:5])
        y_list.append(pat[5])

    X_train = np.array(seq_list, dtype=np.int64)
    y_train = np.array(y_list, dtype=np.int64)

    # Test sequences: half normal, half corrupted with unseen tokens or broken transitions
    X_test_list = []
    y_test_list = []

    # 10 normal
    for i in range(10):
        X_test_list.append(X_train[i])
        y_test_list.append(y_train[i])

    # 10 anomalous: expected next token replaced with unexpected token 99
    for i in range(10):
        X_test_list.append(X_train[i])
        y_test_list.append(99)

    X_test = np.array(X_test_list, dtype=np.int64)
    y_test = np.array(y_test_list, dtype=np.int64)

    return X_train, y_train, X_test, y_test


def test_deeplog_detector(sequence_data: tuple, tmp_path: Path) -> None:
    """Verify DeepLog PyTorch model training, top-k candidate scoring, and persistence."""
    X_train, y_train, X_test, y_test = sequence_data

    detector = DeepLogDetector(
        vocab_size=105,
        top_k=2,
        embedding_dim=16,
        hidden_size=32,
        num_layers=1,
        epochs=15,
        lr=0.01,
        device="cpu",
    )

    detector.fit_sequences(X_train, y_train)
    assert detector.is_fitted is True

    scores = detector.score_sequences(X_test, y_test)
    assert scores.shape == (20,)
    assert np.all((scores >= 0.0) & (scores <= 1.0))

    # Normal test samples (0..9) should have low anomaly scores (mostly 0.0)
    normal_scores = scores[:10]
    # Corrupted test samples (10..19) should have high anomaly scores (> 0.5)
    anom_scores = scores[10:]

    assert np.mean(anom_scores) > np.mean(normal_scores)
    assert np.all(anom_scores >= 0.5)

    # Serialization
    model_path = tmp_path / "deeplog_model"
    detector.save(model_path)
    assert (tmp_path / "deeplog_model.pt").exists()
    assert (tmp_path / "deeplog_model.json").exists()

    reloaded = DeepLogDetector.load(model_path)
    assert reloaded.is_fitted is True
    reloaded_scores = reloaded.score_sequences(X_test, y_test)
    np.testing.assert_array_almost_equal(scores, reloaded_scores)


def test_lstm_autoencoder_detector(tmp_path: Path) -> None:
    """Verify LSTM Autoencoder reconstruction error and persistence."""
    rng = np.random.default_rng(seed=42)

    # 50 normal continuous sequences of length 10
    X_train = rng.normal(loc=0.0, scale=0.5, size=(50, 10))

    detector = LSTMAutoencoderDetector(
        input_dim=1,
        hidden_dim=16,
        latent_dim=8,
        epochs=10,
        lr=0.01,
        device="cpu",
    )
    detector.fit(X_train)
    assert detector.is_fitted is True

    # Test normal vs anomalous sequences
    X_test_normal = rng.normal(loc=0.0, scale=0.5, size=(10, 10))
    X_test_anomalous = rng.normal(loc=5.0, scale=1.0, size=(10, 10))
    X_test = np.vstack([X_test_normal, X_test_anomalous])

    scores = detector.score(X_test)
    assert scores.shape == (20,)
    assert np.all((scores >= 0.0) & (scores <= 1.0))

    # Anomalies should have substantially higher reconstruction loss
    assert np.mean(scores[10:]) > np.mean(scores[:10])

    # Serialization
    model_path = tmp_path / "autoencoder_model"
    detector.save(model_path)
    assert (tmp_path / "autoencoder_model.pt").exists()
    assert (tmp_path / "autoencoder_model.json").exists()

    reloaded = LSTMAutoencoderDetector.load(model_path)
    assert reloaded.is_fitted is True
    reloaded_scores = reloaded.score(X_test)
    np.testing.assert_array_almost_equal(scores, reloaded_scores, decimal=4)


def test_anomaly_ensemble_detector(sequence_data: tuple) -> None:
    """Verify hybrid ensemble combining tabular Isolation Forest and sequential DeepLog."""
    X_train, y_train, X_test, y_test = sequence_data
    rng = np.random.default_rng(seed=42)

    X_tab_train = rng.normal(size=(len(X_train), 5))
    X_tab_test = rng.normal(size=(len(X_test), 5))

    tab_model = IsolationForestDetector(n_estimators=20, random_state=42)
    seq_model = DeepLogDetector(vocab_size=105, epochs=5, device="cpu")

    ensemble = AnomalyEnsembleDetector(
        tabular_detector=tab_model,
        sequential_detector=seq_model,
        weight_tabular=0.5,
        weight_sequential=0.5,
    )

    ensemble.fit_hybrid(X_tab_train, X_train, y_train)
    assert ensemble.is_fitted is True

    scores = ensemble.score_hybrid(X_tab_test, X_test, y_test)
    assert scores.shape == (20,)
    assert np.all((scores >= 0.0) & (scores <= 1.0))
